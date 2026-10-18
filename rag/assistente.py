"""Junta a pesquisa nos PDFs com o modelo da Groq.

Fluxo de cada pergunta:
  1. (Groq, modelo pequeno) reescreve a pergunta tendo em conta a conversa
     e sugere palavras-chave, documento e páginas;
  2. pesquisa os trechos mais relevantes (BM25) e, se a pergunta referir
     uma página, junta a página inteira com os parágrafos numerados;
  3. (Groq, modelo grande) responde só com base nesses trechos, citando [n].
"""

import json
import os
import re

import groq

from .indice import Indice, paginas_mencionadas, remover_referencias
from .pdfs import e_titulo

# A Groq vai retirando modelos, por isso a lista real é pedida à API
# (ver modelos_disponiveis); estas são só as preferências, por ordem.
MODELOS_PREFERIDOS = [
    "openai/gpt-oss-120b",
    "llama-3.3-70b-versatile",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-20b",
]
# para reescrever a pergunta basta um modelo pequeno e rápido
MODELOS_REESCRITA = ["openai/gpt-oss-20b", "llama-3.1-8b-instant"]
# modelos da Groq que não são de conversa (áudio, filtros de segurança, árabe)
_NAO_CONVERSA = ("whisper", "orpheus", "guard", "allam", "tts")
MAX_CARACTERES_CONTEXTO = 12000  # o plano gratuito da Groq limita tokens por minuto

INSTRUCOES = """És um assistente que ajuda um professor de Físico-Química a consultar os seus documentos PDF.

Regras:
- Responde APENAS com base nas FONTES fornecidas na mensagem do utilizador.
- Depois de cada informação, indica a fonte com o número dela entre parênteses retos simples, por exemplo [1] ou [2][3] (não uses 【】 nem outros formatos).
- Quando citares texto do documento, usa aspas e indica o documento e a página.
- Se te pedirem o significado de um trecho ou parágrafo, explica-o por palavras simples. Podes usar conhecimento geral para explicar, mas deixa claro o que está no documento e o que é explicação tua.
- Os parágrafos de uma página completa estão numerados (§1, §2, ...) e os títulos não contam como parágrafos.
- Se a resposta não estiver nas fontes, diz "Não encontrei essa informação nos documentos." e sugere indicar o documento ou a página.
- Responde em português europeu (de Portugal), como nos documentos: "eletrões", "protões", "facto", "tu fazes" — nunca português do Brasil ("elétrons", "fato", "você"). Se a pergunta for noutra língua, responde nessa língua.
- Sê claro e organizado; usa listas quando ajudar."""

INSTRUCOES_REESCRITA = """Preparas pesquisas num conjunto de documentos PDF. Recebes a lista de documentos, o fim da conversa e a nova pergunta.
Devolve APENAS um objeto JSON com:
- "pergunta": a nova pergunta reescrita de forma completa e independente da conversa (resolve "isso", "e na página seguinte?", etc.);
- "palavras_chave": lista de 3 a 8 palavras-chave e sinónimos em português úteis para encontrar a resposta no texto;
- "documento": o nome exato do documento a que a pergunta se refere, ou null se não for claro;
- "paginas": lista de números de página referidos (pela pergunta ou pela conversa), ou [].
"""


def criar_cliente(chave: str | None = None) -> groq.Groq | None:
    chave = chave or os.getenv("GROQ_API_KEY")
    if not chave or chave.startswith("coloca_aqui"):
        return None
    return groq.Groq(api_key=chave)


def modelos_disponiveis(cliente) -> list[str]:
    """Modelos de conversa da conta Groq, com os preferidos primeiro."""
    try:
        ids = [m.id for m in cliente.models.list().data]
    except groq.APIError:
        return MODELOS_PREFERIDOS  # sem ligação: usa a lista fixa
    conversa = [m for m in ids if not any(p in m.lower() for p in _NAO_CONVERSA)]
    return ([m for m in MODELOS_PREFERIDOS if m in conversa]
            + sorted(m for m in conversa if m not in MODELOS_PREFERIDOS)) or MODELOS_PREFERIDOS


def modelo_reescrita(disponiveis: list[str]) -> str:
    return next((m for m in MODELOS_REESCRITA if m in disponiveis), disponiveis[0])


def _opcoes(modelo: str) -> dict:
    """Parâmetros extra para os modelos que "pensam" antes de responder."""
    if modelo.startswith("openai/gpt-oss"):
        return {"reasoning_effort": "low"}  # mais rápido; chega para responder com base nas fontes
    if modelo.startswith("qwen/"):
        return {"reasoning_format": "hidden"}  # não mostrar o raciocínio (<think>) na resposta
    return {}


def explicar_erro(erro: Exception) -> str:
    """Mensagem simples para os erros mais comuns da API."""
    if isinstance(erro, groq.AuthenticationError):
        return "A chave da Groq é inválida. Confirma o GROQ_API_KEY no ficheiro .env."
    if isinstance(erro, groq.RateLimitError):
        return "Limite de pedidos da Groq atingido (plano gratuito). Espera um minuto e tenta outra vez."
    if isinstance(erro, groq.APIConnectionError):
        return "Não foi possível ligar à Groq. Verifica a ligação à internet."
    if isinstance(erro, groq.NotFoundError):
        return "O modelo escolhido não existe ou foi descontinuado. Escolhe outro na barra lateral."
    return f"Erro da Groq: {erro}"


def _historico_curto(historico: list[dict], n: int = 4) -> str:
    linhas = []
    for m in historico[-n:]:
        quem = "Utilizador" if m["papel"] == "user" else "Assistente"
        linhas.append(f"{quem}: {m['conteudo'][:500]}")
    return "\n".join(linhas) or "(sem conversa anterior)"


def reescrever(cliente, modelo: str, pergunta: str, historico: list[dict], indice: Indice) -> dict:
    """Pede ao modelo pequeno para preparar a pesquisa. Em caso de erro devolve {}."""
    lista = "\n".join(f"- {nome} ({indice.num_paginas(nome)} páginas)" for nome in indice.nomes()[:150])
    try:
        resposta = cliente.chat.completions.create(
            model=modelo,
            temperature=0,
            response_format={"type": "json_object"},
            extra_body=_opcoes(modelo),
            messages=[
                {"role": "system", "content": INSTRUCOES_REESCRITA},
                {"role": "user", "content": f"DOCUMENTOS:\n{lista}\n\nCONVERSA:\n{_historico_curto(historico)}\n\nNOVA PERGUNTA: {pergunta}"},
            ],
        )
        dados = json.loads(resposta.choices[0].message.content)
        return dados if isinstance(dados, dict) else {}
    except (groq.APIError, json.JSONDecodeError):
        return {}  # a pesquisa continua só com a pergunta original


def _como_lista(valor) -> list:
    return valor if isinstance(valor, list) else []


def recolher_fontes(indice: Indice, pergunta: str, plano: dict, k: int = 6,
                    filtro=None) -> list[dict]:
    """Escolhe os trechos (e páginas completas) a enviar ao modelo."""
    pergunta_completa = str(plano.get("pergunta") or pergunta)
    palavras_chave = remover_referencias(" ".join(str(p) for p in _como_lista(plano.get("palavras_chave"))))

    # documento referido: pela IA, senão pelo nome escrito na pergunta
    documento = plano.get("documento")
    if documento not in indice.documentos:
        candidatos = (indice.documentos_mencionados(str(documento)) if documento else []) \
            or indice.documentos_mencionados(f"{pergunta} {pergunta_completa}")
        documento = candidatos[0] if candidatos else None
    if filtro:
        if documento not in filtro:
            documento = filtro[0] if len(filtro) == 1 else None

    consulta = remover_referencias(f"{pergunta} {pergunta_completa}")
    trechos = indice.pesquisar(consulta, k=k, documentos=filtro,
                               extra=palavras_chave, preferir=[documento] if documento else [])

    # páginas: as escritas na pergunta têm prioridade sobre as sugeridas pela IA
    paginas = paginas_mencionadas(pergunta)
    if not paginas:
        paginas = [int(p) for p in _como_lista(plano.get("paginas")) if str(p).isdigit()][:3]

    fontes = []
    if paginas:
        # sem documento claro: usa o do melhor trecho (ou o único que existe)
        if not documento:
            nomes = filtro or indice.nomes()
            documento = trechos[0]["documento"] if trechos else (nomes[0] if len(nomes) == 1 else None)
        for num in paginas:
            paragrafos = indice.pagina(documento, num) if documento else []
            if paragrafos:
                fontes.append({"documento": documento, "pagina": num, "tipo": "pagina",
                               "texto": "\n".join(paragrafos)})

    paginas_completas = {(f["documento"], f["pagina"]) for f in fontes}
    fontes += [{**t, "tipo": "trecho"} for t in trechos
               if (t["documento"], t["pagina"]) not in paginas_completas]

    # respeita o limite de tamanho do contexto
    selecionadas, total = [], 0
    for fonte in fontes:
        if total + len(fonte["texto"]) > MAX_CARACTERES_CONTEXTO and selecionadas:
            break
        selecionadas.append(fonte)
        total += len(fonte["texto"])
    return selecionadas


def _formatar_fonte(n: int, fonte: dict) -> str:
    if fonte["tipo"] == "trecho":
        return f"[{n}] Documento \"{fonte['documento']}\", página {fonte['pagina']} (trecho):\n{fonte['texto']}"
    linhas, num = [], 0
    for paragrafo in fonte["texto"].split("\n"):
        if e_titulo(paragrafo):
            linhas.append(f"(título) {paragrafo}")
        else:
            num += 1
            linhas.append(f"§{num} {paragrafo}")
    return f"[{n}] Documento \"{fonte['documento']}\", página {fonte['pagina']} (página completa):\n" + "\n".join(linhas)


def responder(cliente, modelo: str, pergunta: str, fontes: list[dict], historico: list[dict],
              plano: dict, temperatura: float = 0.2):
    """Gera a resposta em streaming (devolve pedaços de texto)."""
    texto_fontes = "\n\n".join(_formatar_fonte(n, f) for n, f in enumerate(fontes, start=1))
    interpretacao = plano.get("pergunta")
    if interpretacao and interpretacao != pergunta:
        pergunta = f"{pergunta}\n(Interpretação da pergunta tendo em conta a conversa: {interpretacao})"

    mensagens = [{"role": "system", "content": INSTRUCOES}]
    for m in historico[-6:]:
        # as citações [n] antigas referem-se a outras fontes: retiram-se
        mensagens.append({"role": m["papel"], "content": re.sub(r"\[\d+\]", "", m["conteudo"])})
    mensagens.append({"role": "user", "content":
                      f"FONTES:\n{texto_fontes or '(nenhum trecho encontrado)'}\n\nPERGUNTA: {pergunta}"})

    stream = cliente.chat.completions.create(
        model=modelo, messages=mensagens, temperature=temperatura, stream=True,
        extra_body=_opcoes(modelo))
    for pedaco in stream:
        if pedaco.choices and pedaco.choices[0].delta.content:
            # os modelos gpt-oss às vezes citam como 【1】: passa a [1]
            yield pedaco.choices[0].delta.content.replace("【", "[").replace("】", "]")
