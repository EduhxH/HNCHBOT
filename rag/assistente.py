import json
import os
import re

import groq

from .indice import Indice
from .texto import (artigos_mencionados, e_seguimento, normalizar, paginas_mencionadas, remover_referencias,
                    texto_simples)

MODELOS_PREFERIDOS = [
    "openai/gpt-oss-120b",
    "llama-3.3-70b-versatile",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-20b",
]
MODELOS_REESCRITA = ["openai/gpt-oss-20b", "qwen/qwen3.8-27b", "llama-3.1-8b-instant"]
_NAO_CONVERSA = ("whisper", "orpheus", "guard", "allam", "tts")
MAX_CARACTERES_CONTEXTO = 8000

INSTRUCOES = """És o assistente de consulta dos documentos oficiais de um agrupamento de escolas (por exemplo, o Regulamento Interno e o Projeto Educativo). Ajudas um professor a encontrar e a interpretar o que os documentos dizem.

Regras:
- Responde APENAS com base nas FONTES da mensagem do utilizador. Não uses conhecimento externo sobre leis ou outras escolas.
- Sê preciso: números, prazos, percentagens, órgãos responsáveis e condições têm de ser exatamente os do texto, com as mesmas unidades (ex.: "dez dias" não é o mesmo que "dez faltas"). Não arredondes nem generalizes.
- Cita sempre: depois de cada informação põe o número da fonte entre parênteses retos simples, ex.: [1] ou [2][3] (não uses 【】). Quando a informação vier de um artigo, indica também o artigo e o número/alínea, ex.: (artigo 118.º, n.º 1, alínea a)) [2].
- Quando te perguntarem o que diz um artigo, ponto ou parágrafo, transcreve as partes relevantes entre aspas e depois explica por palavras simples. Na explicação não acrescentes exemplos, nomes de documentos, órgãos ou regras que não estejam nas fontes.
- Se as fontes só responderem a parte da pergunta, responde a essa parte e diz claramente o que não encontraste.
- Se a resposta não estiver nas fontes, responde só "Não encontrei essa informação nos documentos." e sugere reformular a pergunta ou indicar o artigo/página. Não sugiras outros documentos (regulamentos, leis, planos): só existem os que aparecem nas fontes.
- Quando as fontes enumeram itens que respondem à pergunta (alíneas a), b), c)..., medidas, requisitos, membros), indica-os todos, mesmo que só peçam exemplos.
- Nas tabelas, confirma a linha e a coluna antes de dar um valor.
- Nas páginas completas, os parágrafos estão numerados (§1, §2, ...) e os títulos não contam como parágrafos.
- Responde em português europeu (de Portugal), como nos documentos: "eletrões", "facto", "equipa", "tu fazes" — nunca português do Brasil ("elétrons", "fato", "time", "você"). Se a pergunta for noutra língua, responde nessa língua.
- Sê claro e organizado; usa listas quando ajudar."""

INSTRUCOES_REESCRITA = """Preparas a pesquisa nos documentos de um agrupamento de escolas. Recebes o MAPA dos documentos (grupos de secções, cada um com um código, ex.: G12), o fim da conversa e a nova pergunta.
Devolve APENAS um objeto JSON com:
- "pergunta": a nova pergunta reescrita de forma completa e independente da conversa (resolve "isso", "e o artigo seguinte?", "e na página a seguir?", etc.);
- "palavras_chave": 4 a 10 palavras ou expressões curtas como estariam escritas num documento escolar em português de Portugal, incluindo sinónimos e termos técnicos (ex.: para "quantas vezes posso faltar?" → "limite de faltas", "faltas injustificadas", "excesso de faltas"). Usa o vocabulário formal dos regulamentos, não o do dia a dia nem o do Brasil (ex.: "notas" → "classificações", "chumbar" → "retenção", "pais" → "encarregados de educação", "até quando" → "prazo", "dias úteis", "quem decide" → "compete", "competência");
- "grupos": até 3 códigos do MAPA onde a resposta deve estar, do mais provável para o menos provável (números, estatísticas e metas costumam estar no Projeto Educativo; regras, deveres, prazos e sanções no Regulamento Interno). Se tiveres dúvidas, escolhe grupos de capítulos diferentes;
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
    try:
        ids = [m.id for m in cliente.models.list().data]
    except groq.APIError:
        return MODELOS_PREFERIDOS
    conversa = [m for m in ids if not any(p in m.lower() for p in _NAO_CONVERSA)]
    return ([m for m in MODELOS_PREFERIDOS if m in conversa]
            + sorted(m for m in conversa if m not in MODELOS_PREFERIDOS)) or MODELOS_PREFERIDOS


def modelos_reescrita(disponiveis: list[str]) -> list[str]:
    return [m for m in MODELOS_REESCRITA if m in disponiveis] or disponiveis[:1]


def _opcoes(modelo: str, esforco: str = "low") -> dict:
    if modelo.startswith("openai/gpt-oss"):
        return {"reasoning_effort": esforco}
    if modelo.startswith("qwen/"):
        return {"reasoning_format": "hidden"}
    return {}


def explicar_erro(erro: Exception) -> str:
    if isinstance(erro, groq.AuthenticationError):
        return "A chave da Groq é inválida. Confirma o GROQ_API_KEY no ficheiro .env."
    if isinstance(erro, groq.RateLimitError) and "per day" in str(erro):
        return ("Limite diário de tokens da Groq atingido para este modelo (plano gratuito: 200 000 por dia, "
                "recupera aos poucos ao longo do dia). Escolhe outro modelo na barra lateral ou tenta mais tarde.")
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
    for modelo in modelos:
        try:
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
            return {**dados, "modelo": modelo} if isinstance(dados, dict) else {}
        except (groq.RateLimitError, groq.NotFoundError):
            continue
        except (groq.APIError, json.JSONDecodeError):
            return {}
    return {}


def _como_lista(valor) -> list:
    return valor if isinstance(valor, list) else []


def _documento(indice: Indice, pergunta: str, plano: dict, filtro) -> str | None:
    documento = plano.get("documento")
    if documento not in indice.documentos:
        candidatos = (indice.documentos_mencionados(str(documento)) if documento else []) \
            or indice.documentos_mencionados(f"{pergunta} {plano.get('pergunta') or ''}")
        documento = candidatos[0] if candidatos else None
    if filtro and documento not in filtro:
        documento = filtro[0] if len(filtro) == 1 else None
    return documento


def _fonte_da_pagina(indice: Indice, nome: str, numero: int) -> dict | None:
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
    pergunta_completa = str(plano.get("pergunta") or "")
    documento = _documento(indice, pergunta, plano, filtro)
    documentos = filtro or None
    explicitas = []

    sugeridos = [str(a).upper() for a in _como_lista(plano.get("artigos"))
                 if re.fullmatch(r"\d{1,3}(-[A-Za-z])?", str(a))][:3]
    artigos = artigos_mencionados(pergunta) or (sugeridos if e_seguimento(pergunta) else [])
    for artigo in artigos:
        secoes = indice.secoes_do_artigo(artigo, documentos)
        if documento and len({indice.secao(s)["documento"] for s in secoes}) > 1:
            secoes = [s for s in secoes if indice.secao(s)["documento"] == documento]
        for id_secao in secoes:
            explicitas += [{**t, "tipo": "trecho"} for t in indice.trechos_da_secao(id_secao)]

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

    paginas = paginas_mencionadas(pergunta) or [int(p) for p in _como_lista(plano.get("paginas"))
                                                if str(p).isdigit()][:3]
    nome = documento or (pesquisadas[0]["documento"] if pesquisadas else None) \
        or ((filtro or indice.nomes())[0] if len(filtro or indice.nomes()) == 1 else None)
    for numero in paginas if nome else []:
        fonte = _fonte_da_pagina(indice, nome, numero)
        if fonte:
            explicitas.append(fonte)
    if explicitas:
        pesquisadas = pesquisadas[:2]

    fontes, vistos, total = [], set(), 0
    for fonte in explicitas + pesquisadas:
        if fonte["id"] in vistos:
            continue
        if total + len(fonte["texto"]) > MAX_CARACTERES_CONTEXTO and fontes:
            if fonte in explicitas:
                continue
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
    texto_fontes = "\n\n".join(f"{_cabecalho_fonte(n, f)}\n{f['texto']}" for n, f in enumerate(fontes, start=1))
    interpretacao = plano.get("pergunta")
    if interpretacao and interpretacao != pergunta:
        pergunta = f"{pergunta}\n(Interpretação da pergunta tendo em conta a conversa: {interpretacao})"

    mensagens = [{"role": "system", "content": INSTRUCOES}]
    for m in historico[-4:]:
        mensagens.append({"role": m["papel"], "content": re.sub(r"\[\d+\]", "", m["conteudo"])[:1500]})
    mensagens.append({"role": "user", "content":
                      f"FONTES:\n{texto_fontes or '(nenhum trecho encontrado)'}\n\nPERGUNTA: {pergunta}"})

    stream = cliente.chat.completions.create(
        model=modelo, messages=mensagens, temperature=temperatura, stream=True,
        extra_body=_opcoes(modelo, "medium"))
    pendente = ""
    for pedaco in stream:
        if not (pedaco.choices and pedaco.choices[0].delta.content):
            continue
        pendente += pedaco.choices[0].delta.content
        corte = max(pendente.rfind("["), pendente.rfind("【"))
        if corte >= 0 and "]" not in pendente[corte:] and "】" not in pendente[corte:]:
            pronto, pendente = pendente[:corte], pendente[corte:]
        else:
            pronto, pendente = pendente, ""
        if pronto:
            yield _limpar_resposta(pronto)
    if pendente:
        yield _limpar_resposta(pendente)


_RE_CITACAO = re.compile(r'“([^”]+)”|«([^»]+)»|"([^"\n]+)"')
_RE_LINHA_CITADA = re.compile(r"^[ \t]*>[ \t>]*(.*)$", re.M)
_RE_ROTULO = re.compile(r"^\s*\*\*[^*]{1,60}\*\*\s*[–—:.-]?\s*")
_RE_REFERENCIA = re.compile(r"\((?:artigos?|art\.|n\.?\s*[ºo°]|al[íi]nea|ponto|p[áa]gina|p[áa]g\.)"
                            r"[^()]*(?:\([^()]*\)[^()]*)*\)", re.I)
_RE_OMISSAO = re.compile(r"[(\[]?\s*(?:\.{3}|…)\s*[)\]]?")
_RE_MARCADOR = re.compile(r"(?<![\w.])(?:[a-z]|[ivx]+|\d{1,2})\s*\)|(?<![\w.])\d{1,2}\s*[—–]\s")
MIN_PALAVRAS_CITACAO = 3


def _palavras(texto: str) -> str:
    texto = re.sub(r"</?[a-z]+[^>]*>|\[\d+\]|§\d+|\(título\)", " ", texto)
    texto = _RE_MARCADOR.sub(" ", normalizar(texto_simples(texto)))
    return " ".join(re.findall(r"[a-z0-9]+", texto))


def citacoes(resposta: str) -> list[tuple[str, list[str]]]:
    linhas = [_RE_ROTULO.sub("", m.group(1)) for m in _RE_LINHA_CITADA.finditer(resposta)]
    entre_aspas = [next(g for g in m.groups() if g is not None)
                   for m in _RE_CITACAO.finditer(_RE_LINHA_CITADA.sub("", resposta))]
    encontradas = []
    for citacao in linhas + entre_aspas:
        citacao = citacao.strip()
        texto = _RE_REFERENCIA.sub(" … ", citacao)
        partes = [p for p in map(_palavras, _RE_OMISSAO.split(texto)) if p]
        if sum(len(p.split()) for p in partes) >= MIN_PALAVRAS_CITACAO:
            encontradas.append((citacao, partes))
    return encontradas


def verificar_citacoes(resposta: str, fontes: list[dict], historico=(), pergunta: str = "") -> list[str]:
    fontes = list(fontes) + [f for m in list(historico)[-4:] for f in m.get("fontes", [])]
    base = " " + " ".join(_palavras(f"{_cabecalho_fonte(1, f)}\n{f['texto']}") for f in fontes) + " "
    base += _palavras(pergunta) + " "
    em_falta = [citacao for citacao, partes in citacoes(resposta)
                if not all(f" {parte} " in base for parte in partes)]
    return list(dict.fromkeys(em_falta))


def _limpar_resposta(texto: str) -> str:
    texto = texto.replace("【", "[").replace("】", "]")
    texto = re.sub(r"\[(\d+)†[^\]]*\]", r"[\1]", texto)
    return texto.replace(" ", " ").replace(" ", " ").replace("‑", "-")
