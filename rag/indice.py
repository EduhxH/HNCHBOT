"""Índice de pesquisa sobre todos os PDFs da pasta `documentos/`.

Cada PDF é lido uma única vez: o texto extraído fica guardado em
`dados/indice.json` e só volta a ser lido se o ficheiro mudar.

A pesquisa usa BM25 (pesquisa por palavras-chave, a mesma ideia dos
motores de busca clássicos). Não precisa de modelos de embeddings,
que a Groq não disponibiliza, por isso funciona em qualquer PC.
"""

import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from .pdfs import dividir_em_trechos, extrair_paginas

RAIZ = Path(__file__).resolve().parent.parent
PASTA_DOCUMENTOS = RAIZ / "documentos"
FICHEIRO_INDICE = RAIZ / "dados" / "indice.json"
VERSAO = 1  # aumenta se mudares a forma como os PDFs são lidos

# parâmetros clássicos do BM25
K1, B = 1.5, 0.75


def normalizar(texto: str) -> str:
    """Minúsculas e sem acentos: "Reações" -> "reacoes"."""
    texto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


# palavras demasiado comuns para ajudar na pesquisa
STOPWORDS = {normalizar(p) for p in """
a à às ao aos as com como da das de do dos e é em entre era essa esse esta este
eu ele ela eles elas foi há isso isto já lhe mais mas me mesmo muito na nas não
no nos nós num numa o os ou para pela pelas pelo pelos por qual quais quando que
quem se sem ser seu sua seus suas são também te tem tu teu tua um uma umas uns
vos você onde sobre dele dela meu minha
página páginas pág pag paragrafo parágrafo parágrafos trecho texto documento
documentos pdf significa significado explica explicar diz dizer fala falar
quero saber sabes podes pode diga mostra mostrar
""".split()}

_PLURAIS = (("oes", "ao"), ("aes", "ao"), ("ais", "al"), ("eis", "el"),
            ("ois", "ol"), ("res", "r"), ("zes", "z"), ("ns", "m"), ("s", ""))


def _radical(palavra: str) -> str:
    """Reduz plurais e género: "reações"/"reação" -> "reaca", "forças" -> "forc"."""
    if palavra.isdigit() or len(palavra) <= 3:
        return palavra
    if len(palavra) == 4:
        return palavra[:-1] if palavra.endswith("s") and not palavra.endswith("ss") else palavra
    for fim, troca in _PLURAIS:
        if palavra.endswith(fim):
            palavra = palavra[: -len(fim)] + troca
            break
    if len(palavra) > 4 and palavra[-1] in "aeo":
        palavra = palavra[:-1]
    return palavra


def tokenizar(texto: str) -> list[str]:
    palavras = []
    for palavra in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", normalizar(texto)):
        partes = palavra.split("-")
        palavras += partes
        if len(partes) > 1:  # "ácido-base" conta como "acido", "base" e "acidobase"
            palavras.append("".join(partes))
    return [_radical(p) for p in palavras
            if p not in STOPWORDS and (len(p) > 1 or p.isdigit())]


_RE_PAGINA = re.compile(
    r"\b(?:paginas?|pags?\.?|pgs?\.?|p\.)\s*(\d{1,4})(?:\s*(?:a|-|–|e|ate)\s*(\d{1,4}))?")


def paginas_mencionadas(pergunta: str) -> list[int]:
    """Encontra referências como "página 12", "pág. 3 a 5" ou "p. 7"."""
    paginas = []
    for m in _RE_PAGINA.finditer(normalizar(pergunta)):
        inicio = int(m.group(1))
        fim = int(m.group(2) or inicio)
        if fim < inicio:
            inicio, fim = fim, inicio
        paginas.extend(range(inicio, min(fim, inicio + 2) + 1))
    return list(dict.fromkeys(paginas))[:3]  # no máximo 3 páginas


_RE_ORDINAL = re.compile(
    r"\b\d{1,3}\s*\.?\s*[ºª°]|\b(?:primeir|segund|terceir|quart|quint|sext|penultim|ultim)[oa]s?"
    r"(?=\s+(?:paragrafo|linha|frase|pagina))")


def remover_referencias(texto: str) -> str:
    """Tira "página 3", "2.º", "segundo parágrafo"... (estes números não ajudam a pesquisa)."""
    texto = _RE_PAGINA.sub(" ", normalizar(texto))
    return _RE_ORDINAL.sub(" ", texto)


def _listar_pdfs(pasta: Path) -> list[Path]:
    pasta.mkdir(parents=True, exist_ok=True)
    return sorted(p for p in pasta.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")


def _assinatura(caminho: Path) -> str:
    info = caminho.stat()
    return f"{info.st_size}-{info.st_mtime_ns}"


def assinatura_pasta(pasta: Path = PASTA_DOCUMENTOS) -> tuple:
    """Muda sempre que um PDF é adicionado, removido ou alterado."""
    return tuple((p.relative_to(pasta).as_posix(), _assinatura(p)) for p in _listar_pdfs(pasta))


def sincronizar(pasta: Path = PASTA_DOCUMENTOS, ficheiro: Path = FICHEIRO_INDICE,
                progresso=None) -> dict:
    """Lê os PDFs novos ou alterados e devolve {nome: {"paginas": [...], ...}}.

    `progresso(n, total, nome)` é chamado antes de ler cada PDF novo.
    """
    cache = {}
    if ficheiro.exists():
        try:
            dados = json.loads(ficheiro.read_text(encoding="utf-8"))
            if dados.get("versao") == VERSAO:
                cache = dados["documentos"]
        except (json.JSONDecodeError, KeyError):
            pass  # índice corrompido: volta a ler tudo

    pdfs = _listar_pdfs(pasta)
    documentos, mudou = {}, False
    for n, caminho in enumerate(pdfs, start=1):
        nome = caminho.relative_to(pasta).as_posix()
        assinatura = _assinatura(caminho)
        anterior = cache.get(nome)
        if anterior and anterior["assinatura"] == assinatura:
            documentos[nome] = anterior
            continue
        if progresso:
            progresso(n, len(pdfs), nome)
        try:
            paginas, erro = extrair_paginas(caminho), None
        except ValueError as e:  # PDF protegido por palavra-passe
            paginas, erro = [], str(e)
        except Exception:  # o PyMuPDF não conseguiu abrir o ficheiro
            paginas, erro = [], "ficheiro danificado ou não é um PDF válido"
        documentos[nome] = {"assinatura": assinatura, "paginas": paginas, "erro": erro}
        mudou = True

    if mudou or set(cache) != set(documentos):
        ficheiro.parent.mkdir(parents=True, exist_ok=True)
        ficheiro.write_text(json.dumps({"versao": VERSAO, "documentos": documentos},
                                       ensure_ascii=False), encoding="utf-8")
    return documentos


class Indice:
    """Guarda os trechos de todos os PDFs e pesquisa-os com BM25."""

    def __init__(self, documentos: dict, pasta: Path = PASTA_DOCUMENTOS):
        self.documentos = documentos
        self.pasta = pasta
        self.trechos = []
        for nome, doc in documentos.items():
            self.trechos += dividir_em_trechos(nome, doc["paginas"])

        # índice invertido: termo -> [(nº do trecho, frequência)]
        self._ocorrencias = defaultdict(list)
        self._comprimento = []
        for i, trecho in enumerate(self.trechos):
            frequencias = Counter(tokenizar(trecho["texto"]))
            self._comprimento.append(sum(frequencias.values()))
            for termo, n in frequencias.items():
                self._ocorrencias[termo].append((i, n))

        total = len(self.trechos)
        self._media = sum(self._comprimento) / total if total else 1
        self._idf = {termo: math.log(1 + (total - len(lista) + 0.5) / (len(lista) + 0.5))
                     for termo, lista in self._ocorrencias.items()}

    def nomes(self) -> list[str]:
        return list(self.documentos)

    def caminho(self, nome: str) -> Path:
        return self.pasta / nome

    def num_paginas(self, nome: str) -> int:
        return len(self.documentos[nome]["paginas"])

    def pagina(self, nome: str, numero: int) -> list[str]:
        """Parágrafos da página `numero` (começa em 1); lista vazia se não existir."""
        paginas = self.documentos.get(nome, {}).get("paginas", [])
        return paginas[numero - 1] if 1 <= numero <= len(paginas) else []

    def documentos_mencionados(self, texto: str) -> list[str]:
        """Documentos cujo nome aparece no texto, do mais provável para o menos."""
        termos = set(tokenizar(texto))
        pontos = {}
        for nome in self.documentos:
            palavras = {t for t in tokenizar(Path(nome).stem) if len(t) >= 3}
            if palavras and termos & palavras:
                pontos[nome] = len(termos & palavras) / len(palavras)
        return sorted(pontos, key=pontos.get, reverse=True)

    def pesquisar(self, consulta: str, k: int = 6, documentos=None,
                  extra: str = "", preferir=(), minimo_relativo: float = 0.3) -> list[dict]:
        """Devolve os `k` trechos mais relevantes.

        consulta   – a pergunta (peso total)
        extra      – palavras-chave/sinónimos sugeridos pela IA (meio peso)
        documentos – se indicado, só pesquisa nestes documentos
        preferir   – documentos mencionados na pergunta (ganham um bónus)
        minimo_relativo – descarta trechos com menos de 30% da pontuação do melhor
        """
        pesos = {t: 1.0 for t in tokenizar(consulta)}
        for t in tokenizar(extra):
            pesos.setdefault(t, 0.5)

        pontos = defaultdict(float)
        for termo, peso in pesos.items():
            for i, freq in self._ocorrencias.get(termo, ()):
                norma = K1 * (1 - B + B * self._comprimento[i] / self._media)
                pontos[i] += peso * self._idf[termo] * freq * (K1 + 1) / (freq + norma)

        resultados = []
        for i, valor in pontos.items():
            nome = self.trechos[i]["documento"]
            if documentos and nome not in documentos:
                continue
            if nome in preferir:
                valor *= 1.3
            resultados.append((valor, i))
        resultados.sort(reverse=True)
        if resultados:
            limite = resultados[0][0] * minimo_relativo
            resultados = [(v, i) for v, i in resultados if v >= limite]
        return [{**self.trechos[i], "pontuacao": round(v, 2)} for v, i in resultados[:k]]
