"""Lê todos os PDFs da pasta documentos/ antes de abrir o chatbot.

A primeira leitura demora (cerca de 1 minuto por cada 150 páginas). Aqui vê-se
o progresso no terminal; depois o chatbot abre logo, porque o resultado fica
guardado em dados/indice.json.

Uso:  python indexar.py
"""

from collections import Counter

from rag.indice import Indice, sincronizar


def progresso(nome, pagina, total):
    print(f"  {nome}: página {pagina} de {total}", flush=True)


if __name__ == "__main__":
    indice = Indice(sincronizar(progresso=progresso))
    secoes = Counter(s["documento"] for s in indice.secoes)
    artigos = Counter(s["documento"] for s in indice.secoes if s["artigo"])
    for nome, doc in indice.documentos.items():
        if doc["erro"]:
            print(f"ERRO em {nome}: {doc['erro']}")
            continue
        print(f"{indice.titulo(nome)} ({nome}): {doc['num_paginas']} páginas, "
              f"{secoes[nome]} secções, {artigos[nome]} artigos")
        for aviso in doc.get("avisos", []):
            print(f"  aviso: {aviso}")
    print(f"Pronto: {len(indice.trechos)} trechos para pesquisa.")
