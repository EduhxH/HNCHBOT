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
