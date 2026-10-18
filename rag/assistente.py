"""Junta a pesquisa nos PDFs com os modelos da Groq.

Fluxo de cada pergunta:
  1. (Groq, modelo pequeno) reescreve a pergunta tendo em conta a conversa,
     sugere palavras-chave como estariam escritas no documento e escolhe,
     no mapa dos documentos, os capítulos/secções onde procurar;
  2. junta as fontes: artigos e páginas pedidos explicitamente vão inteiros;
     o resto vem da pesquisa BM25, com bónus para as secções escolhidas;
  3. (Groq, modelo grande) responde só com base nessas fontes, citando [n],
     o artigo e o número/alínea.
"""

import json
import os
import re

import groq

from .indice import Indice
from .texto import artigos_mencionados, e_seguimento, paginas_mencionadas, remover_referencias

# A Groq vai retirando modelos, por isso a lista real é pedida à API
# (ver modelos_disponiveis); estas são só as preferências, por ordem.
MODELOS_PREFERIDOS = [
    "openai/gpt-oss-120b",
    "llama-3.3-70b-versatile",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-20b",
]
# para preparar a pesquisa basta um modelo pequeno e rápido
MODELOS_REESCRITA = ["openai/gpt-oss-20b", "qwen/qwen3.8-27b", "llama-3.1-8b-instant"]
# modelos da Groq que não são de conversa (áudio, filtros de segurança, árabe)
_NAO_CONVERSA = ("whisper", "orpheus", "guard", "allam", "tts")
# o plano gratuito da Groq permite 8000 tokens por minuto em cada modelo:
# ~8000 caracteres de fontes são ~2500 tokens
MAX_CARACTERES_CONTEXTO = 8000

INSTRUCOES = """És o assistente de consulta dos documentos oficiais de um agrupamento de escolas (por exemplo, o Regulamento Interno e o Projeto Educativo). Ajudas um professor a encontrar e a interpretar o que os documentos dizem.

Regras:
- Responde APENAS com base nas FONTES da mensagem do utilizador. Não uses conhecimento externo sobre leis ou outras escolas.
- Sê preciso: números, prazos, percentagens, órgãos responsáveis e condições têm de ser exatamente os do texto, com as mesmas unidades (ex.: "dez dias" não é o mesmo que "dez faltas"). Não arredondes nem generalizes.
- Cita sempre: depois de cada informação põe o número da fonte entre parênteses retos simples, ex.: [1] ou [2][3] (não uses 【】). Quando a informação vier de um artigo, indica também o artigo e o número/alínea, ex.: (artigo 118.º, n.º 1, alínea a)) [2].
- Quando te perguntarem o que diz um artigo, ponto ou parágrafo, transcreve as partes relevantes entre aspas e depois explica por palavras simples. Na explicação não acrescentes exemplos, nomes de documentos, órgãos ou regras que não estejam nas fontes.
- Se as fontes só responderem a parte da pergunta, responde a essa parte e diz claramente o que não encontraste.
- Se a resposta não estiver nas fontes, responde só "Não encontrei essa informação nos documentos." e sugere reformular a pergunta ou indicar o artigo/página. Não sugiras outros documentos (regulamentos, leis, planos): só existem os que aparecem nas fontes.
- Nas tabelas, confirma a linha e a coluna antes de dar um valor.
- Nas páginas completas, os parágrafos estão numerados (§1, §2, ...) e os títulos não contam como parágrafos.
- Responde em português europeu (de Portugal), como nos documentos: "eletrões", "facto", "equipa", "tu fazes" — nunca português do Brasil ("elétrons", "fato", "time", "você"). Se a pergunta for noutra língua, responde nessa língua.
- Sê claro e organizado; usa listas quando ajudar."""

INSTRUCOES_REESCRITA = """Preparas a pesquisa nos documentos de um agrupamento de escolas. Recebes o MAPA dos documentos (grupos de secções, cada um com um código, ex.: G12), o fim da conversa e a nova pergunta.
Devolve APENAS um objeto JSON com:
- "pergunta": a nova pergunta reescrita de forma completa e independente da conversa (resolve "isso", "e o artigo seguinte?", "e na página a seguir?", etc.);
- "palavras_chave": 4 a 10 palavras ou expressões curtas como estariam escritas num documento escolar em português de Portugal, incluindo sinónimos e termos técnicos (ex.: para "quantas vezes posso faltar?" → "limite de faltas", "faltas injustificadas", "excesso de faltas");
- "grupos": até 3 códigos do MAPA onde a resposta deve estar, do mais provável para o menos provável;
- "documento": o nome do ficheiro a que a pergunta se refere, ou null se não for claro;
- "artigos": números de artigos referidos pela pergunta ou pela conversa (ex.: "120", "58-A"), ou [];
- "paginas": números de página referidos pela pergunta ou pela conversa, ou [].

MAPA:
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


def modelos_reescrita(disponiveis: list[str]) -> list[str]:
    """Modelos para preparar a pesquisa, por ordem (o seguinte é usado se o limite do anterior acabar)."""
    return [m for m in MODELOS_REESCRITA if m in disponiveis] or disponiveis[:1]


def _opcoes(modelo: str, esforco: str = "low") -> dict:
    """Parâmetros extra para os modelos que "pensam" antes de responder."""
    if modelo.startswith("openai/gpt-oss"):
        return {"reasoning_effort": esforco}
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
        linhas.append(f"{quem}: {m['conteudo'][:400]}")
    return "\n".join(linhas) or "(sem conversa anterior)"


def reescrever(cliente, modelos: list[str], pergunta: str, historico: list[dict], indice: Indice) -> dict:
    """Pede ao modelo pequeno para preparar a pesquisa. Em caso de erro devolve {}."""
    for modelo in modelos:
        try:
            # sem novas tentativas: se o limite acabou, passa logo ao modelo seguinte
            resposta = cliente.with_options(max_retries=0).chat.completions.create(
                model=modelo,
                temperature=0,
                response_format={"type": "json_object"},
                extra_body=_opcoes(modelo),
                messages=[
                    {"role": "system", "content": INSTRUCOES_REESCRITA + indice.mapa()},
                    {"role": "user", "content": f"CONVERSA:\n{_historico_curto(historico)}\n\nNOVA PERGUNTA: {pergunta}"},
                ],
            )
            dados = json.loads(resposta.choices[0].message.content)
            return dados if isinstance(dados, dict) else {}
        except (groq.RateLimitError, groq.NotFoundError):
            continue
        except (groq.APIError, json.JSONDecodeError):
            return {}  # a pesquisa continua só com a pergunta original
    return {}


def _como_lista(valor) -> list:
    return valor if isinstance(valor, list) else []


def _documento(indice: Indice, pergunta: str, plano: dict, filtro) -> str | None:
    """Documento a que a pergunta se refere: o indicado pela IA, senão o nome escrito na pergunta."""
    documento = plano.get("documento")
    if documento not in indice.documentos:
        candidatos = (indice.documentos_mencionados(str(documento)) if documento else []) \
            or indice.documentos_mencionados(f"{pergunta} {plano.get('pergunta') or ''}")
        documento = candidatos[0] if candidatos else None
    if filtro and documento not in filtro:
        documento = filtro[0] if len(filtro) == 1 else None
    return documento


def _fonte_da_pagina(indice: Indice, nome: str, numero: int) -> dict | None:
    """A página inteira, com os parágrafos numerados (§1, §2, ...)."""
    linhas, n = [], 0
    for el in indice.elementos_da_pagina(nome, numero):
        if el["tipo"] == "titulo":
            linhas.append(f"(título) {el['texto']}")
        elif el["tipo"] == "tabela":
            linhas.append(el["texto"])
        else:
            n += 1
            linhas.append(f"§{n} {el['texto']}")
    if not linhas:
        return None
    return {"id": f"{nome}#p{numero}", "tipo": "pagina", "documento": nome,
            "titulo_doc": indice.titulo(nome), "rotulo": f"Página {numero} (completa)", "caminho": "",
            "pagina": numero, "pagina_fim": numero, "texto": "\n\n".join(linhas)}


def recolher_fontes(indice: Indice, pergunta: str, plano: dict, k: int = 6, filtro=None) -> list[dict]:
    """Escolhe as fontes a enviar ao modelo, por ordem de prioridade e até ao limite de tamanho."""
    pergunta_completa = str(plano.get("pergunta") or "")
    documento = _documento(indice, pergunta, plano, filtro)
    documentos = filtro or None
    explicitas = []

    # 1) artigos pedidos: escritos na pergunta ou, numa pergunta de seguimento, indicados pela IA
    #    (noutras perguntas, os artigos que a IA sugere são só uma pista para a pesquisa)
    sugeridos = [str(a).upper() for a in _como_lista(plano.get("artigos"))
                 if re.fullmatch(r"\d{1,3}(-[A-Za-z])?", str(a))][:3]
    artigos = artigos_mencionados(pergunta) or (sugeridos if e_seguimento(pergunta) else [])
    for artigo in artigos:
        secoes = indice.secoes_do_artigo(artigo, documentos)
        if documento and len({indice.secao(s)["documento"] for s in secoes}) > 1:
            secoes = [s for s in secoes if indice.secao(s)["documento"] == documento]
        for id_secao in secoes:
            explicitas += [{**t, "tipo": "trecho"} for t in indice.trechos_da_secao(id_secao)]

    # 2) pesquisa por palavras, com bónus para as secções que a IA escolheu no mapa
    escolhidas = indice.secoes_dos_grupos(_como_lista(plano.get("grupos"))[:3])
    escolhidas |= {s for a in sugeridos for s in indice.secoes_do_artigo(a, documentos)}
    palavras_chave = " ".join(str(p) for p in _como_lista(plano.get("palavras_chave")))
    consulta = remover_referencias(f"{pergunta} {pergunta_completa}")
    pontos = []
    for i, valor in indice.pontuar(consulta, remover_referencias(palavras_chave)).items():
        trecho = indice.trechos[i]
        if documentos and trecho["documento"] not in documentos:
            continue
        valor *= 1.6 if trecho["secao"] in escolhidas else 1
        valor *= 1.3 if trecho["documento"] == documento else 1
        pontos.append((valor, i))
    pontos.sort(reverse=True)
    limite = pontos[0][0] * 0.25 if pontos else 0
    pesquisadas = [{**indice.trechos[i], "tipo": "trecho"} for v, i in pontos[:k] if v >= limite]

    # 3) páginas pedidas: a página inteira (sem documento indicado, a do melhor resultado)
    paginas = paginas_mencionadas(pergunta) or [int(p) for p in _como_lista(plano.get("paginas"))
                                                if str(p).isdigit()][:3]
    nome = documento or (pesquisadas[0]["documento"] if pesquisadas else None) \
        or ((filtro or indice.nomes())[0] if len(filtro or indice.nomes()) == 1 else None)
    for numero in paginas if nome else []:
        fonte = _fonte_da_pagina(indice, nome, numero)
        if fonte:
            explicitas.append(fonte)
    if explicitas:  # pediu um artigo/página concreto: só 2 resultados da pesquisa, como contexto
        pesquisadas = pesquisadas[:2]

    # junta tudo sem repetir e sem passar o limite de tamanho
    fontes, vistos, total = [], set(), 0
    for fonte in explicitas + pesquisadas:
        if fonte["id"] in vistos:
            continue
        if total + len(fonte["texto"]) > MAX_CARACTERES_CONTEXTO and fontes:
            if fonte in explicitas:
                continue  # um artigo grande pode não caber todo; tenta o resto
            break
        vistos.add(fonte["id"])
        fontes.append({**fonte, "titulo_doc": indice.titulo(fonte["documento"])})
        total += len(fonte["texto"])
    return fontes


def _cabecalho_fonte(n: int, fonte: dict) -> str:
    paginas = (f"página {fonte['pagina']}" if fonte["pagina"] == fonte["pagina_fim"]
               else f"páginas {fonte['pagina']}-{fonte['pagina_fim']}")
    partes = [f"[{n}] {fonte['titulo_doc']}"]
    if fonte.get("caminho"):
        partes.append(fonte["caminho"])
    rotulo = fonte["rotulo"]
    if fonte.get("partes", 1) > 1:
        rotulo += f" (parte {fonte['parte']} de {fonte['partes']})"
    partes.append(rotulo)
    return " › ".join(partes) + f" — {paginas}"


def responder(cliente, modelo: str, pergunta: str, fontes: list[dict], historico: list[dict],
              plano: dict, temperatura: float = 0.1):
    """Gera a resposta em streaming (devolve pedaços de texto)."""
    texto_fontes = "\n\n".join(f"{_cabecalho_fonte(n, f)}\n{f['texto']}" for n, f in enumerate(fontes, start=1))
    interpretacao = plano.get("pergunta")
    if interpretacao and interpretacao != pergunta:
        pergunta = f"{pergunta}\n(Interpretação da pergunta tendo em conta a conversa: {interpretacao})"

    mensagens = [{"role": "system", "content": INSTRUCOES}]
    for m in historico[-4:]:
        # as citações [n] antigas referem-se a outras fontes: retiram-se
        mensagens.append({"role": m["papel"], "content": re.sub(r"\[\d+\]", "", m["conteudo"])[:1500]})
    mensagens.append({"role": "user", "content":
                      f"FONTES:\n{texto_fontes or '(nenhum trecho encontrado)'}\n\nPERGUNTA: {pergunta}"})

    # "medium": um pouco mais de raciocínio dá citações mais completas e fiéis às fontes
    stream = cliente.chat.completions.create(
        model=modelo, messages=mensagens, temperature=temperatura, stream=True,
        extra_body=_opcoes(modelo, "medium"))
    pendente = ""
    for pedaco in stream:
        if not (pedaco.choices and pedaco.choices[0].delta.content):
            continue
        pendente += pedaco.choices[0].delta.content
        # uma citação pode vir partida em vários pedaços: guarda o que vem depois de um "[" aberto
        corte = max(pendente.rfind("["), pendente.rfind("【"))
        if corte >= 0 and "]" not in pendente[corte:] and "】" not in pendente[corte:]:
            pronto, pendente = pendente[:corte], pendente[corte:]
        else:
            pronto, pendente = pendente, ""
        if pronto:
            yield _limpar_resposta(pronto)
    if pendente:
        yield _limpar_resposta(pendente)


def _limpar_resposta(texto: str) -> str:
    """Os modelos gpt-oss às vezes citam como 【1】 ou [1†L1-L3]: passa tudo a [1]."""
    texto = texto.replace("【", "[").replace("】", "]")
    texto = re.sub(r"\[(\d+)†[^\]]*\]", r"[\1]", texto)
    return texto.replace(" ", " ").replace(" ", " ").replace("‑", "-")
