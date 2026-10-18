"""Leitura de PDFs.

Cada PDF é convertido em markdown, página a página, pelo pymupdf4llm com a
análise de layout do pymupdf-layout: junta as linhas em parágrafos, marca
títulos e listas e reconstrói as tabelas. Depois disso:
  - as tabelas mal reconstruídas são trocadas pela leitura da grelha da
    tabela (PyMuPDF), quando esta é melhor;
  - palavras que ficaram coladas ("residenteporgrandes") são separadas;
  - cabeçalhos/rodapés repetidos e páginas de índice são retirados.

O resultado é uma lista de "elementos" (títulos, parágrafos e tabelas) pela
ordem de leitura, cada um com a página onde aparece.
"""

import re
import unicodedata
from collections import Counter

import pymupdf
import pymupdf.layout  # noqa: F401  (ativa a análise de layout no pymupdf4llm)
import pymupdf4llm

from .texto import normalizar, texto_simples

PAGINAS_POR_LOTE = 10  # para poder mostrar o progresso em PDFs grandes
_RE_PALAVRA = re.compile(r"[^\W\d_]+")
_RE_INDICE = re.compile(r"\.{5,}\s*\d*\s*$")  # "Artigo 3.º (Objetivos) ........ 18"
_RE_LISTA = re.compile(r"^\s*[-*]\s")


def extrair_documento(caminho, progresso=None) -> dict:
    """Lê o PDF e devolve {"titulo", "num_paginas", "elementos", "avisos"}.

    `progresso(pagina, total)` é chamado à medida que as páginas são lidas.
    """
    with pymupdf.open(caminho) as doc:
        if doc.needs_pass:
            raise ValueError("PDF protegido por palavra-passe")
        total = doc.page_count
        paginas, avisos = [], []
        for inicio in range(0, total, PAGINAS_POR_LOTE):
            if progresso:
                progresso(inicio, total)
            lote = list(range(inicio, min(inicio + PAGINAS_POR_LOTE, total)))
            for numero, parte in zip(lote, pymupdf4llm.to_markdown(doc, pages=lote, page_chunks=True)):
                pagina = doc[numero]
                conhecidas = _palavras_da_pagina(pagina)
                markdown = _separar_palavras_coladas(parte["text"], conhecidas)
                markdown = _corrigir_tabelas(markdown, pagina, conhecidas)
                markdown = _limpar_markdown(markdown)
                em_falta = _palavras_em_falta(pagina, markdown)
                if em_falta >= 5:
                    avisos.append(f"página {numero + 1}: {em_falta} palavras do PDF não foram lidas")
                paginas.append(markdown)
        if progresso:
            progresso(total, total)
        titulo = (_titulo(doc[0]) if total else "") or doc.metadata.get("title") or ""

    paginas = _sem_cabecalhos_rodapes(paginas)
    elementos = []
    for numero, markdown in enumerate(paginas, start=1):
        elementos += _elementos_da_pagina(numero, markdown)
    return {"titulo": titulo, "num_paginas": total,
            "elementos": _juntar_entre_paginas(elementos), "avisos": avisos}


# ---------------------------------------------------------------- palavras

def _palavras_da_pagina(pagina) -> set[str]:
    """Palavras que existem mesmo na página (servem para validar o markdown)."""
    palavras = set()
    for palavra in pagina.get_text("words"):
        palavras.update(p.lower() for p in _RE_PALAVRA.findall(palavra[4]))
    return palavras


def _segmentar(palavra: str, conhecidas: set[str]) -> list[str] | None:
    """Divide "residenteporgrandes" em ["residente", "por", "grandes"] (o menor nº de partes)."""
    baixa, n = palavra.lower(), len(palavra)
    melhor = [None] * (n + 1)
    melhor[0] = []
    for fim in range(1, n + 1):
        for inicio in range(max(0, fim - 30), fim):
            pedaco = baixa[inicio:fim]
            if melhor[inicio] is None or pedaco not in conhecidas:
                continue
            if len(pedaco) == 1 and pedaco not in "aeoàé":
                continue
            candidato = melhor[inicio] + [(inicio, fim)]
            if melhor[fim] is None or len(candidato) < len(melhor[fim]):
                melhor[fim] = candidato
    if not melhor[n] or len(melhor[n]) < 2:
        return None
    return [palavra[i:f] for i, f in melhor[n]]


def _separar_palavras_coladas(texto: str, conhecidas: set[str]) -> str:
    def separar(m):
        palavra = m.group(0)
        if len(palavra) < 7 or palavra.lower() in conhecidas:
            return palavra
        partes = _segmentar(palavra, conhecidas)
        return " ".join(partes) if partes else palavra
    return _RE_PALAVRA.sub(separar, texto)


def _qualidade(texto: str, conhecidas: set[str]) -> float:
    """Fração das palavras do texto que existem na página (palavras partidas baixam-na)."""
    palavras = [p.lower() for p in _RE_PALAVRA.findall(texto_simples(texto)) if len(p) >= 3]
    return sum(p in conhecidas for p in palavras) / len(palavras) if palavras else 1.0


def _palavras_em_falta(pagina, markdown: str) -> int:
    no_pdf = Counter(p.lower() for p in _RE_PALAVRA.findall(pagina.get_text()) if len(p) >= 3)
    lidas = Counter(p.lower() for p in _RE_PALAVRA.findall(texto_simples(markdown)) if len(p) >= 3)
    return sum((no_pdf - lidas).values())


# ---------------------------------------------------------------- tabelas

def _corrigir_tabelas(markdown: str, pagina, conhecidas: set[str]) -> str:
    """Troca tabelas com palavras partidas pela leitura da grelha, se for melhor."""
    linhas = markdown.split("\n")
    blocos, i = [], 0  # blocos de linhas seguidas que começam por "|"
    while i < len(linhas):
        if linhas[i].startswith("|"):
            j = i
            while j < len(linhas) and linhas[j].startswith("|"):
                j += 1
            blocos.append((i, j))
            i = j
        else:
            i += 1

    grelhas = None
    for inicio, fim in reversed(blocos):
        tabela = "\n".join(linhas[inicio:fim])
        qualidade = _qualidade(tabela, conhecidas)
        if qualidade >= 0.9:
            continue
        if grelhas is None:
            grelhas = [_separar_palavras_coladas(_grelha_markdown(t), conhecidas) for t in _grelhas(pagina)]
        # o markdown às vezes junta duas tabelas seguidas: compara também com 2-3 grelhas juntas
        candidatas = ["\n\n".join(grelhas[i:j]) for i in range(len(grelhas))
                      for j in range(i + 1, min(i + 3, len(grelhas)) + 1)]
        # escolhe a candidata com as mesmas palavras (F1: nem palavras a menos nem a mais)
        palavras = {p for p in _RE_PALAVRA.findall(tabela.lower()) if p in conhecidas}
        melhor, semelhanca = None, 0.5
        for candidata in candidatas:
            outras = set(_RE_PALAVRA.findall(candidata.lower()))
            comum = len(palavras & outras)
            f1 = 2 * comum / (len(palavras) + len(outras)) if comum else 0
            if f1 > semelhanca:
                melhor, semelhanca = candidata, f1
        if (melhor and _qualidade(melhor, conhecidas) > qualidade + 0.03
                and melhor.count("\n") <= 1.5 * (fim - inicio) + 2):
            linhas[inicio:fim] = melhor.split("\n")
    return "\n".join(linhas)


def _grelhas(pagina) -> list[list[list[str]]]:
    """Tabelas com linhas desenhadas, lidas pela grelha: [tabela][linha][célula]."""
    # a análise de layout muda a deteção de tabelas; aqui queremos só a grelha
    layout = pymupdf._get_layout
    pymupdf._get_layout = None
    try:
        tabelas = pagina.find_tables(strategy="lines").tables
    finally:
        pymupdf._get_layout = layout

    # o texto de cada célula vem das palavras da página (com os espaços certos)
    palavras = pagina.get_text("words")

    def texto_da_caixa(caixa):
        dentro = sorted((p for p in palavras
                         if caixa.contains(pymupdf.Point((p[0] + p[2]) / 2, (p[1] + p[3]) / 2))),
                        key=lambda p: (p[5], p[6], p[7]))  # bloco, linha, palavra
        return " ".join(p[4] for p in dentro)

    resultado = []
    for tabela in tabelas:
        caixas = [[pymupdf.Rect(c) if c else None for c in linha.cells] for linha in tabela.rows]
        inicio_coluna = {c: caixa.x0 for linha in caixas for c, caixa in enumerate(linha) if caixa}
        inicio_linha = {r: next((c.y0 for c in linha if c), None) for r, linha in enumerate(caixas)}
        textos = [[texto_da_caixa(c) if c else None for c in linha] for linha in caixas]
        # célula vazia (None) = coberta por uma célula fundida. Se a fusão é vertical,
        # repete-se o texto de cima (ex.: "1º Ciclo" para o 1.º, 2.º, 3.º e 4.º ano)
        for r, linha in enumerate(caixas):
            for c, caixa in enumerate(linha):
                if caixa is not None:
                    continue
                horizontal = any(linha[e] and linha[e].x1 > inicio_coluna.get(c, 1e9) + 1 for e in range(c))
                cima = next((r2 for r2 in range(r - 1, -1, -1) if caixas[r2][c]), None)
                vertical = (cima is not None and inicio_linha[r] is not None
                            and caixas[cima][c].y1 > inicio_linha[r] + 1)
                textos[r][c] = textos[cima][c] if vertical and not horizontal else ""
        resultado.append(textos)
    return resultado


def _grelha_markdown(linhas: list[list]) -> str:
    """Tabela (lista de linhas de células) em markdown; células fundidas vêm vazias."""
    linhas = [[re.sub(r"\s+", " ", c or "").strip().replace("|", "/") for c in linha] for linha in linhas]
    if not linhas:
        return ""
    colunas = [j for j in range(len(linhas[0])) if any(linha[j] for linha in linhas)]
    linhas = [[linha[j] for j in colunas] for linha in linhas if any(linha)]
    if not linhas or len(colunas) < 2:
        return ""
    md = []
    if len(linhas) > 1 and sum(bool(c) for c in linhas[0]) == 1:  # 1.ª linha = título da tabela
        md.append(f"**{next(c for c in linhas[0] if c)}**")  # sem linha em branco: fica com a tabela
        linhas = linhas[1:]
    md.append("|" + "|".join(linhas[0]) + "|")
    md.append("|" + "---|" * len(colunas))
    md += ["|" + "|".join(linha) + "|" for linha in linhas[1:]]
    return "\n".join(md)


# ---------------------------------------------------------------- limpeza

def _limpar_markdown(markdown: str) -> str:
    # alguns PDFs guardam "ç" como "c" + cedilha separada: junta-os ("Subsecção")
    markdown = unicodedata.normalize("NFC", markdown)
    # texto dentro de imagens/esquemas (ex.: organograma): fica, mas assinalado
    markdown = re.sub(r"<!--\s*Start of picture text\s*-->(.*?)<!--\s*End of picture text\s*-->",
                      lambda m: "\n\n*[Texto de uma imagem ou esquema; a ordem pode não ser a original]:* "
                                + m.group(1).replace("<br>", " · ").strip(" ·") + "\n\n",
                      markdown, flags=re.S)
    markdown = re.sub(r"<!--.*?-->|^==> picture .* <==$", "", markdown, flags=re.S | re.M)
    markdown = markdown.replace("­", "")  # hífen invisível
    markdown = re.sub(r"\s*‑\s*", "-", markdown)  # hífen não separável ("pré ‑ escolar")
    return markdown


def _chave(linha: str) -> str:
    return re.sub(r"\d+", "#", normalizar(texto_simples(linha))).strip()


_RE_ESTRUTURA = re.compile(r"^(cap[ií]tulo|sec[cç][aã]o|subsec[cç][aã]o|artigo|anexo)\b", re.I)


def _sem_cabecalhos_rodapes(paginas: list[str]) -> list[str]:
    """Retira linhas que se repetem no topo/fundo de muitas páginas e os números de página."""
    def margens(markdown):
        linhas = [l for l in markdown.split("\n") if l.strip()]
        return linhas[:2] + linhas[-2:]

    contagem = Counter()
    for markdown in paginas:
        contagem.update({_chave(l) for l in margens(markdown)})
    # os números são trocados por "#" ("Página # de #"); por isso, títulos como
    # "Artigo #.º" também podem parecer repetidos e nunca contam como rodapé
    repetidas = {c for c, n in contagem.items()
                 if c and n >= max(3, 0.5 * len(paginas)) and not _RE_ESTRUTURA.match(c)}
    repetidas.add("#")  # número de página sozinho

    resultado = []
    for markdown in paginas:
        candidatas = set(margens(markdown))
        resultado.append("\n".join(l for l in markdown.split("\n")
                                   if not (l in candidatas and _chave(l) in repetidas)))
    return resultado


def _titulo(pagina) -> str:
    """Título da capa: a linha mais curta entre as de letra maior ("REGULAMENTO INTERNO")."""
    linhas = []
    for bloco in pagina.get_text("dict")["blocks"]:
        for linha in bloco.get("lines", []):
            texto = "".join(s["text"] for s in linha["spans"]).strip()
            if len(texto) >= 5 and any(c.isalpha() for c in texto):
                linhas.append((max(s["size"] for s in linha["spans"]), texto))
    if not linhas:
        return ""
    maior = max(tamanho for tamanho, _ in linhas)
    titulo = min((t for tamanho, t in linhas if tamanho >= maior - 0.5), key=len)
    pequenas = {"de", "da", "do", "das", "dos", "e", "a", "o", "em", "para"}
    return " ".join(p if p in pequenas and i else p.capitalize()
                    for i, p in enumerate(titulo.lower().split()))


# ---------------------------------------------------------------- elementos

def _e_titulo(bloco: str) -> bool:
    if not bloco or "\n" in bloco or len(bloco) > 250 or bloco.startswith("|"):
        return False
    if bloco.startswith("#"):
        return True
    return bool(re.fullmatch(r"\*\*[^*].*\*\*", bloco)) and len(texto_simples(bloco)) <= 200


def _elementos_da_pagina(numero: int, markdown: str) -> list[dict]:
    linhas = [l for l in markdown.split("\n") if l.strip()]
    if linhas and sum(bool(_RE_INDICE.search(texto_simples(l))) for l in linhas) >= 0.4 * len(linhas):
        return []  # página de índice: só repete os títulos, sem conteúdo
    elementos = []
    for bloco in re.split(r"\n\s*\n", markdown):
        bloco = "\n".join(l.rstrip() for l in bloco.strip("\n").split("\n")
                          if l.strip() and not _RE_INDICE.search(texto_simples(l)))
        if not bloco.strip():
            continue
        if any(l.lstrip().startswith("|") for l in bloco.split("\n")):
            tipo, texto = "tabela", bloco.strip()
        elif _e_titulo(bloco.strip()):
            tipo, texto = "titulo", texto_simples(bloco)
        else:
            tipo, texto = "texto", bloco.strip()
        if texto_simples(texto):
            elementos.append({"pagina": numero, "pagina_fim": numero, "tipo": tipo, "texto": texto})
    return elementos


_LIGACOES = {"de", "da", "do", "das", "dos", "e", "a", "o", "na", "no", "nas", "nos", "em",
             "para", "com", "ao", "aos", "à", "às", "pela", "pelo", "pelas", "pelos", "ou"}


def _titulo_continua(anterior: str, seguinte: str) -> bool:
    """Título partido em duas linhas: "... Ultrapassagem dos" + "limites de Faltas",
    "Secção V — ... e Manuais" + "Escolares"."""
    ultima = anterior.split()[-1].lower() if anterior.split() else ""
    if ultima in _LIGACOES or seguinte[:1].islower():
        return True
    # numa secção/subsecção com nome, uma palavra solta na linha seguinte é o resto do nome
    return (bool(re.match(r"(?i)(sub)?sec[çc][ãa]o\s+\S+\s*[—–-]\s*\S", anterior))
            and len(seguinte.split()) == 1 and not seguinte.startswith("("))


def _juntar_entre_paginas(elementos: list[dict]) -> list[dict]:
    """Junta títulos partidos em duas linhas e parágrafos partidos pelo fim da página."""
    resultado = []
    for el in elementos:
        anterior = resultado[-1] if resultado else None
        if (anterior and anterior["tipo"] == el["tipo"] == "titulo"
                and anterior["pagina_fim"] == el["pagina"] and _titulo_continua(anterior["texto"], el["texto"])):
            anterior["texto"] += " " + el["texto"]
        elif (anterior and anterior["tipo"] == el["tipo"] == "texto"
                and el["pagina"] == anterior["pagina_fim"] + 1
                and not texto_simples(anterior["texto"]).endswith((".", ":", ";", "!", "?"))
                and re.match(r"[a-zà-ú]", el["texto"])):
            anterior["texto"] += " " + el["texto"]
            anterior["pagina_fim"] = el["pagina"]
        else:
            resultado.append(el)
    return resultado


# ---------------------------------------------------------------- imagem

def imagem_pagina(caminho, pagina: int, destacar: str = "", zoom: float = 1.6) -> bytes:
    """Desenha a página como PNG, com o texto `destacar` marcado a amarelo."""
    with pymupdf.open(caminho) as doc:
        pag = doc[pagina - 1]
        # procura frase a frase (frases inteiras costumam ser únicas na página)
        for frase in re.split(r"(?<=[.!?;:])\s+|\n", texto_simples(destacar)):
            # o hífen pode estar guardado de outra forma no PDF: tenta também
            # os pedaços entre hífenes, do maior para o menor
            for pedaco in [frase] + sorted(frase.split("-"), key=len, reverse=True)[:2]:
                pedaco = pedaco.strip()
                if len(pedaco) < 20:
                    break
                retangulos = pag.search_for(pedaco[:150])
                for retangulo in retangulos:
                    pag.add_highlight_annot(retangulo)
                if retangulos:
                    break
        pixmap = pag.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), annots=True)
        return pixmap.tobytes("png")
