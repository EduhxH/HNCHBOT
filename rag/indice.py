import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from .estrutura import construir_secoes, dividir_em_trechos
from .pdfs import extrair_documento
from .texto import texto_simples, tokenizar

RAIZ = Path(__file__).resolve().parent.parent
PASTA_DOCUMENTOS = RAIZ / "documentos"
FICHEIRO_INDICE = RAIZ / "dados" / "indice.json"
VERSAO = 3

K1, B = 1.5, 0.75


def _listar_pdfs(pasta: Path) -> list[Path]:
    pasta.mkdir(parents=True, exist_ok=True)
    return sorted(p for p in pasta.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")


def _assinatura(caminho: Path) -> str:
    info = caminho.stat()
    return f"{info.st_size}-{info.st_mtime_ns}"


def assinatura_pasta(pasta: Path = PASTA_DOCUMENTOS) -> tuple:
    return tuple((p.relative_to(pasta).as_posix(), _assinatura(p)) for p in _listar_pdfs(pasta))


def sincronizar(pasta: Path = PASTA_DOCUMENTOS, ficheiro: Path = FICHEIRO_INDICE,
                progresso=None) -> dict:
    cache = {}
    if ficheiro.exists():
        try:
            dados = json.loads(ficheiro.read_text(encoding="utf-8"))
            if dados.get("versao") == VERSAO:
                cache = dados["documentos"]
        except (json.JSONDecodeError, KeyError):
            pass

    documentos, mudou = {}, False
    for caminho in _listar_pdfs(pasta):
        nome = caminho.relative_to(pasta).as_posix()
        assinatura = _assinatura(caminho)
        anterior = cache.get(nome)
        if anterior and anterior["assinatura"] == assinatura:
            documentos[nome] = anterior
            continue
        aviso = (lambda pagina, total, nome=nome: progresso(nome, pagina, total)) if progresso else None
        try:
            lido, erro = extrair_documento(caminho, aviso), None
        except ValueError as e:
            lido, erro = {}, str(e)
        except Exception:
            lido, erro = {}, "ficheiro danificado ou não é um PDF válido"
        documentos[nome] = {"titulo": "", "num_paginas": 0, "elementos": [], "avisos": [], "paginas_ocr": [],
                            **lido, "assinatura": assinatura, "erro": erro}
        mudou = True

    if mudou or set(cache) != set(documentos):
        ficheiro.parent.mkdir(parents=True, exist_ok=True)
        ficheiro.write_text(json.dumps({"versao": VERSAO, "documentos": documentos},
                                       ensure_ascii=False), encoding="utf-8")
    return documentos


def _curto(rotulo: str) -> str:
    rotulo = re.sub(r"^Artigo\s+", "Art. ", rotulo)
    rotulo = re.sub(r"[()]", "", rotulo)
    return rotulo if len(rotulo) <= 100 else rotulo[:97] + "..."


class Indice:
    def __init__(self, documentos: dict, pasta: Path = PASTA_DOCUMENTOS):
        self.documentos = documentos
        self.pasta = pasta
        self.secoes, self.trechos = [], []
        for nome, doc in documentos.items():
            for secao in construir_secoes(nome, doc["elementos"]):
                secao["id"] = f"S{len(self.secoes) + 1}"
                self.secoes.append(secao)
                self.trechos += [t for t in dividir_em_trechos(secao) if len(texto_simples(t["texto"])) >= 40]
        self._termos_titulos = {t for t in tokenizar(" ".join(f"{Path(n).stem} {self.titulo(n)}" for n in documentos))
                                if t.isalpha() and len(t) >= 3}
        self._secoes = {s["id"]: s for s in self.secoes}
        self._trechos_da_secao = defaultdict(list)
        for trecho in self.trechos:
            self._trechos_da_secao[trecho["secao"]].append(trecho)

        self.grupos, chaves = [], {}
        for secao in self.secoes:
            if secao["tipo"] == "artigo":
                chave = (secao["documento"], secao["caminho"])
            else:
                chave = (secao["documento"], " › ".join(filter(None, [secao["caminho"], secao["rotulo"]])))
            if chave not in chaves:
                chaves[chave] = {"id": f"G{len(self.grupos) + 1}", "documento": chave[0],
                                 "caminho": chave[1], "secoes": []}
                self.grupos.append(chaves[chave])
            chaves[chave]["secoes"].append(secao["id"])
            secao["grupo"] = chaves[chave]["id"]
        self._grupos = {g["id"]: g for g in self.grupos}

        self._ocorrencias = defaultdict(list)
        self._comprimento = []
        for i, t in enumerate(self.trechos):
            frequencias = Counter(tokenizar(f"{t['rotulo']} {t['rotulo']} {t['caminho']} {t['texto']}"))
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

    def titulo(self, nome: str) -> str:
        return self.documentos.get(nome, {}).get("titulo") or Path(nome).stem

    def num_paginas(self, nome: str) -> int:
        return self.documentos[nome].get("num_paginas", 0)

    def lido_por_ocr(self, fonte: dict) -> bool:
        return any(fonte["pagina"] <= p <= fonte["pagina_fim"]
                   for p in self.documentos.get(fonte["documento"], {}).get("paginas_ocr", []))

    def documentos_mencionados(self, texto: str) -> list[str]:
        termos = set(tokenizar(texto))
        pontos = {}
        for nome in self.documentos:
            palavras = {t for t in tokenizar(f"{Path(nome).stem} {self.titulo(nome)}") if len(t) >= 3}
            if palavras and termos & palavras:
                pontos[nome] = len(termos & palavras) / len(palavras)
        return sorted(pontos, key=pontos.get, reverse=True)

    def secao(self, id_secao: str) -> dict | None:
        return self._secoes.get(id_secao)

    def trechos_da_secao(self, id_secao: str) -> list[dict]:
        return self._trechos_da_secao.get(id_secao, [])

    def secoes_do_artigo(self, numero: str, documentos=None) -> list[str]:
        numero = numero.upper()
        return [s["id"] for s in self.secoes
                if s["artigo"] and (s["artigo"] == numero or s["artigo"].startswith(numero + "-"))
                and (not documentos or s["documento"] in documentos)]

    def elementos_da_pagina(self, nome: str, numero: int) -> list[dict]:
        return [e for e in self.documentos.get(nome, {}).get("elementos", [])
                if e["pagina"] <= numero <= e["pagina_fim"]]

    def secoes_dos_grupos(self, ids_grupos) -> set[str]:
        return {s for g in ids_grupos if g in self._grupos for s in self._grupos[g]["secoes"]}

    def mapa(self) -> str:
        linhas = []
        for nome in self.nomes():
            linhas.append(f"## {self.titulo(nome)} (ficheiro {nome})")
            anterior = []
            for grupo in (g for g in self.grupos if g["documento"] == nome):
                partes = grupo["caminho"].split(" › ") if grupo["caminho"] else ["(início)"]
                muda = next((i for i, (a, b) in enumerate(zip(anterior, partes)) if a != b),
                            min(len(anterior), len(partes)))
                muda = min(muda, len(partes) - 1)
                linhas += [f"# {_curto(parte)}" for parte in partes[muda:-1]]
                anterior = partes
                artigos = [self._secoes[s]["artigo"] for s in grupo["secoes"] if self._secoes[s]["artigo"]]
                intervalo = f" (art. {artigos[0]}–{artigos[-1]})" if len(artigos) > 1 else \
                    f" (art. {artigos[0]})" if artigos else ""
                linhas.append(f"{grupo['id']} {_curto(partes[-1])}{intervalo}")
        return "\n".join(linhas)

    def pontuar(self, consulta: str, extra: str = "") -> dict[int, float]:
        pesos = {t: 1.0 for t in tokenizar(consulta)}
        for t in tokenizar(extra):
            pesos.setdefault(t, 0.5)
        for t in self._termos_titulos:
            pesos.pop(t, None)
        pontos = defaultdict(float)
        for termo, peso in pesos.items():
            for i, freq in self._ocorrencias.get(termo, ()):
                norma = K1 * (1 - B + B * self._comprimento[i] / self._media)
                pontos[i] += peso * self._idf[termo] * freq * (K1 + 1) / (freq + norma)
        return pontos

    def pesquisar(self, consulta: str, k: int = 6, documentos=None, extra: str = "",
                  preferir=(), minimo_relativo: float = 0.3) -> list[dict]:
        resultados = []
        for i, valor in self.pontuar(consulta, extra).items():
            nome = self.trechos[i]["documento"]
            if documentos and nome not in documentos:
                continue
            resultados.append((valor * (1.3 if nome in preferir else 1), i))
        resultados.sort(reverse=True)
        if resultados:
            limite = resultados[0][0] * minimo_relativo
            resultados = [(v, i) for v, i in resultados if v >= limite]
        return [{**self.trechos[i], "pontuacao": round(v, 2)} for v, i in resultados[:k]]
