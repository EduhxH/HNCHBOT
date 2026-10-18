"""Lê todos os PDFs da pasta documentos/ antes de abrir o chatbot.

Útil quando há muitos PDFs: mostra o progresso no terminal, e o chatbot
depois abre logo, porque o texto já fica guardado em dados/indice.json.

Uso:  python indexar.py
"""

from rag.indice import Indice, sincronizar


def progresso(n, total, nome):
    print(f"[{n}/{total}] a ler {nome}...")


if __name__ == "__main__":
    indice = Indice(sincronizar(progresso=progresso))
    paginas = sum(indice.num_paginas(n) for n in indice.nomes())
    print(f"Pronto: {len(indice.nomes())} PDF(s), {paginas} páginas, {len(indice.trechos)} trechos.")
    for nome, doc in indice.documentos.items():
        if doc["erro"]:
            print(f"  ERRO em {nome}: {doc['erro']}")
