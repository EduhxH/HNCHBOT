import re

from .texto import texto_simples

TAMANHO_TRECHO = 1800

_NUMERAL = r"[IVXLC]+|\d+"
_ESTRUTURA = [
    (1, "capitulo", re.compile(rf"^cap[íi]tulo\s+({_NUMERAL})\b\s*[-–—.:]?\s*(.*)$", re.I)),
    (2, "seccao", re.compile(rf"^sec[çc][ãa]o\s+({_NUMERAL})\b\s*[-–—.:]?\s*(.*)$", re.I)),
    (3, "subseccao", re.compile(rf"^subsec[çc][ãa]o\s+({_NUMERAL})\b\s*[-–—.:]?\s*(.*)$", re.I)),
    (4, "artigo", re.compile(r"^artigo\s+(\d+)\s*\.?\s*[ºo°]?\s*(-\s*[A-Z]\b)?\s*[-–—.:]?\s*(.*)$", re.I)),
]


def _estrutura(titulo: str):
    for nivel, tipo, regex in _ESTRUTURA:
        m = regex.match(titulo)
        if m and tipo == "artigo":
            return nivel, tipo, m.group(1) + (m.group(2) or "").replace(" ", "").upper(), m.group(3)
        if m:
            return nivel, tipo, m.group(1).upper(), m.group(2)
    return None


def _completa_titulo(secao: dict, el: dict, texto: str) -> bool:
    if secao["tipo"] == "artigo":
        return len(texto) < 250 and texto.startswith("(") and texto.endswith(")")
    if secao["tipo"] in ("capitulo", "seccao", "subseccao"):
        return el["tipo"] == "titulo" and texto.isupper()
    return False


def construir_secoes(nome: str, elementos: list[dict]) -> list[dict]:
    secoes, pilha = [], []
    atual = None

    def abrir(nivel, rotulo, el, tipo, artigo=None, completo=True):
        nonlocal atual
        while pilha and pilha[-1][0] >= nivel:
            pilha.pop()
        atual = {"documento": nome, "rotulo": rotulo, "caminho": " › ".join(r for _, r in pilha),
                 "tipo": tipo, "artigo": artigo, "completo": completo, "elementos": [],
                 "pagina": el["pagina"], "pagina_fim": el["pagina_fim"]}
        pilha.append((nivel, rotulo))
        secoes.append(atual)

    for el in elementos:
        texto = el["texto"] if el["tipo"] == "titulo" else texto_simples(el["texto"])
        if atual and not atual["completo"] and not atual["elementos"] and _completa_titulo(atual, el, texto):
            atual["rotulo"] += (" " if atual["tipo"] == "artigo" else " — ") + texto
            atual["completo"] = True
            pilha[-1] = (pilha[-1][0], atual["rotulo"])
            continue
        if el["tipo"] == "titulo":
            estrutura = _estrutura(texto)
            if estrutura:
                nivel, tipo, numero, resto = estrutura
                abrir(nivel, texto, el, tipo, artigo=numero if tipo == "artigo" else None,
                      completo=bool(resto.strip()))
                continue
            if (not atual or atual["tipo"] != "artigo") and not texto.endswith(":"):
                abrir(2 if texto.isupper() else 3, texto, el, "titulo")
                continue
        if atual is None:
            abrir(1, "Início do documento", el, "titulo")
        atual["elementos"].append(el)
        atual["pagina_fim"] = max(atual["pagina_fim"], el["pagina_fim"])
    return [s for s in secoes if s["elementos"]]


def formatar_elemento(el: dict) -> str:
    return f"**{el['texto']}**" if el["tipo"] == "titulo" else el["texto"]


def _dividir_tabela(el: dict) -> list[dict]:
    linhas = el["texto"].split("\n")
    separador = next((i for i, l in enumerate(linhas) if re.fullmatch(r"\|(\s*:?-+:?\s*\|)+\s*", l)), None)
    if not separador:
        return [el]
    cabecalho, partes, atual = linhas[:separador + 1], [], []
    for linha in linhas[separador + 1:]:
        if atual and len("\n".join(cabecalho + atual)) + len(linha) > TAMANHO_TRECHO:
            partes.append(atual)
            atual = []
        atual.append(linha)
    if atual:
        partes.append(atual)
    return [{**el, "texto": "\n".join(cabecalho + parte)} for parte in partes]


def dividir_em_trechos(secao: dict) -> list[dict]:
    pedacos = []
    for el in secao["elementos"]:
        grande = el["tipo"] == "tabela" and len(el["texto"]) > TAMANHO_TRECHO
        pedacos += _dividir_tabela(el) if grande else [el]

    grupos, atual, tamanho = [], [], 0
    for pedaco in pedacos:
        if atual and tamanho + len(pedaco["texto"]) > TAMANHO_TRECHO:
            grupos.append(atual)
            atual, tamanho = [], 0
        atual.append(pedaco)
        tamanho += len(pedaco["texto"])
    if atual:
        grupos.append(atual)

    return [{"id": f"{secao['id']}.{n}", "secao": secao["id"], "documento": secao["documento"],
             "rotulo": secao["rotulo"], "caminho": secao["caminho"], "artigo": secao["artigo"],
             "parte": n, "partes": len(grupos),
             "pagina": min(e["pagina"] for e in grupo), "pagina_fim": max(e["pagina_fim"] for e in grupo),
             "texto": "\n\n".join(formatar_elemento(e) for e in grupo)}
            for n, grupo in enumerate(grupos, start=1)]
