import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymupdf  # noqa: E402

from rag.indice import PASTA_DOCUMENTOS  # noqa: E402
from rag.pdfs import (_copia_sem_texto, _imagens_repetidas, _linhas_ocr, _tessdata, _zonas_ocr,  # noqa: E402
                      extrair_documento)
from rag.texto import normalizar, texto_simples  # noqa: E402

COBERTURA_MINIMA_TEXTO = 0.97
COBERTURA_MINIMA_IMAGEM = 0.8


def palavras(texto: str) -> set[str]:
    return {p for p in re.findall(r"[a-z0-9]+", normalizar(texto_simples(texto))) if len(p) >= 4}


def verificar(caminho: Path, tessdata: str | None) -> tuple[list[str], Counter]:
    lido = extrair_documento(caminho)
    indexado = defaultdict(set)
    for el in lido["elementos"]:
        for numero in range(el["pagina"], el["pagina_fim"] + 1):
            indexado[numero] |= palavras(el["texto"])
    falhas, contagem = [], Counter(avisos=len(lido["avisos"]), paginas_ocr=len(lido["paginas_ocr"]))
    todo_o_indice = set().union(*indexado.values())
    with pymupdf.open(caminho) as doc:
        frequencia = Counter(p for pagina in doc for p in palavras(pagina.get_text()))
        margens = {p for p, n in frequencia.items() if n >= max(3, doc.page_count / 2)}
        nativas = lidas = 0
        for pagina in doc:
            if indexado[pagina.number + 1]:
                esperadas = palavras(pagina.get_text()) - margens
                nativas += len(esperadas)
                lidas += len(esperadas & (indexado[pagina.number + 1] | todo_o_indice))
        if nativas and lidas / nativas < COBERTURA_MINIMA_TEXTO:
            falhas.append(f"só {lidas / nativas:.1%} do texto nativo chegou ao índice")
        contagem["texto_nativo"] = round(100 * lidas / nativas, 1) if nativas else 100.0
        if not tessdata:
            return falhas, contagem
        repetidas = _imagens_repetidas(doc)
        for pagina in doc:
            contagem["imagens_repetidas"] += sum(i["xref"] in repetidas and pymupdf.Rect(i["bbox"]).width >= 24
                                                 and pymupdf.Rect(i["bbox"]).height >= 8
                                                 for i in pagina.get_image_info(xrefs=True))
            zonas = _zonas_ocr(pagina, repetidas)
            if not zonas:
                continue
            copia = _copia_sem_texto(pagina)
            for zona in zonas:
                aceites = palavras(" ".join(texto for _, texto in _linhas_ocr(copia[0], zona, tessdata)))
                if not aceites:
                    contagem["imagens_sem_texto_aceite"] += 1
                    continue
                cobertura = len(aceites & indexado[pagina.number + 1]) / len(aceites)
                contagem["imagens_lidas"] += cobertura >= COBERTURA_MINIMA_IMAGEM
                if cobertura < COBERTURA_MINIMA_IMAGEM:
                    falhas.append(f"página {pagina.number + 1}: só {cobertura:.0%} do texto da imagem "
                                  f"{[round(v) for v in zona]} chegou ao índice")
    return falhas, contagem


def main():
    pasta = Path(sys.argv[1]) if len(sys.argv) > 1 else PASTA_DOCUMENTOS
    tessdata = _tessdata()
    if not tessdata:
        print("Sem tessdata/por.traineddata: só é verificado o texto nativo.")
    total, com_falhas = Counter(), 0
    for caminho in sorted(p for p in pasta.rglob("*") if p.suffix.lower() == ".pdf"):
        inicio = time.time()
        falhas, contagem = verificar(caminho, tessdata)
        total.update({k: v for k, v in contagem.items() if k != "texto_nativo"})
        com_falhas += bool(falhas)
        print(f"{'OK    ' if not falhas else 'FALHOU'} {caminho.name} ({time.time() - inicio:.0f}s): "
              f"texto nativo {contagem['texto_nativo']}%, {contagem['imagens_lidas']} imagens lidas, "
              f"{contagem['imagens_sem_texto_aceite']} sem texto legível, {contagem['imagens_repetidas']} repetidas "
              f"ignoradas, OCR em {contagem['paginas_ocr']} páginas, {contagem['avisos']} avisos"
              + "".join(f"\n       {falha}" for falha in falhas), flush=True)
    print(f"{com_falhas} PDF(s) com falhas | {total['imagens_lidas']} imagens lidas, "
          f"{total['imagens_sem_texto_aceite']} sem texto legível, {total['imagens_repetidas']} repetidas ignoradas, "
          f"OCR em {total['paginas_ocr']} páginas, {total['avisos']} avisos")
    sys.exit(1 if com_falhas else 0)


if __name__ == "__main__":
    main()
