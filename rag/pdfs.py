"""Leitura de PDFs: extrai o texto página a página, dividido em parágrafos."""

import re

import pymupdf

# Tamanho aproximado (em caracteres) de cada trecho usado na pesquisa.
TAMANHO_TRECHO = 1200


def _limpar(texto: str) -> str:
    """Junta as linhas de um bloco e remove espaços repetidos."""
    # muitos PDFs guardam o hífen como "soft hyphen" (U+00AD)
    texto = texto.replace("­", "-")
    # palavra partida no fim da linha: "calcula-\nse" -> "calcula-se"
    texto = re.sub(r"-[ \t]*\n\s*", "-", texto)
    return re.sub(r"\s+", " ", texto).strip()


def e_titulo(paragrafo: str) -> bool:
    """Heurística: blocos curtos sem pontuação final costumam ser títulos."""
    return len(paragrafo) < 90 and not paragrafo.endswith((".", ":", ";", "?", "!", ","))


def extrair_paginas(caminho) -> list[list[str]]:
    """Devolve uma lista com os parágrafos de cada página.

    resultado[0] são os parágrafos da página 1, resultado[1] da página 2, etc.
    Cada "parágrafo" é um bloco de texto tal como o PDF o organiza.
    """
    paginas = []
    with pymupdf.open(caminho) as doc:
        if doc.needs_pass:
            raise ValueError("PDF protegido por palavra-passe")
        for pagina in doc:
            paragrafos = []
            for bloco in pagina.get_text("blocks", sort=True):
                if bloco[6] != 0:  # 0 = texto, 1 = imagem
                    continue
                texto = _limpar(bloco[4])
                # ignora blocos vazios e números de página soltos
                if len(texto) < 2 or re.fullmatch(r"\d{1,4}", texto):
                    continue
                paragrafos.append(texto)
            paginas.append(paragrafos)
    return paginas


def dividir_em_trechos(nome: str, paginas: list[list[str]]) -> list[dict]:
    """Agrupa parágrafos seguidos da mesma página em trechos de ~TAMANHO_TRECHO."""
    trechos = []
    for num_pagina, paragrafos in enumerate(paginas, start=1):
        atual = []
        for paragrafo in paragrafos:
            if atual and sum(map(len, atual)) + len(paragrafo) > TAMANHO_TRECHO:
                # um título no fim do trecho passa para o trecho seguinte
                seguinte = [atual.pop()] if len(atual) > 1 and e_titulo(atual[-1]) else []
                trechos.append(_trecho(nome, num_pagina, atual))
                atual = seguinte
            atual.append(paragrafo)
        if atual:
            trechos.append(_trecho(nome, num_pagina, atual))
    return trechos


def _trecho(nome, pagina, paragrafos) -> dict:
    return {"documento": nome, "pagina": pagina, "texto": "\n".join(paragrafos)}


def imagem_pagina(caminho, pagina: int, destacar: str = "", zoom: float = 1.6) -> bytes:
    """Desenha a página como PNG, com o texto `destacar` marcado a amarelo."""
    with pymupdf.open(caminho) as doc:
        pag = doc[pagina - 1]
        # procura frase a frase (frases inteiras costumam ser únicas na página)
        for frase in re.split(r"(?<=[.!?;:])\s+|\n", destacar):
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
