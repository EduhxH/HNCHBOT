import re
import unicodedata


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def texto_simples(markdown: str) -> str:
    texto = re.sub(r"<br\s*/?>", " ", markdown)
    texto = re.sub(r"^\s*#+\s*|^\s*[-*]\s+(?=\S)", "", texto, flags=re.M)
    texto = re.sub(r"[*_`|]+", " ", texto)
    return re.sub(r"[ \t]+", " ", texto).strip()


STOPWORDS = {normalizar(p) for p in """
a à às ao aos as com como da das de do dos e é em entre era essa esse esta este
eu ele ela eles elas foi há isso isto já lhe mais mas me mesmo muito na nas não
no nos nós num numa o os ou para pela pelas pelo pelos por qual quais quando que
quem se sem ser seu sua seus suas são também te tem tu teu tua um uma umas uns
vos você onde sobre dele dela meu minha br
página páginas pág pag paragrafo parágrafo parágrafos trecho texto documento
documentos pdf significa significado explica explicar diz dizer fala falar
quero saber sabes podes pode diga mostra mostrar
""".split()}

_PLURAIS = (("oes", "ao"), ("aes", "ao"), ("ais", "al"), ("eis", "el"),
            ("ois", "ol"), ("res", "r"), ("zes", "z"), ("ns", "m"), ("s", ""))


def _radical(palavra: str) -> str:
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
    for palavra in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", normalizar(re.sub(r"<br\s*/?>", " ", texto))):
        partes = palavra.split("-")
        palavras += partes
        if len(partes) > 1:
            palavras.append("".join(partes))
    return [_radical(p) for p in palavras
            if p not in STOPWORDS and (len(p) > 1 or p.isdigit())]


_RE_PAGINA = re.compile(
    r"\b(?:paginas?|pags?\.?|pgs?\.?|p\.)\s*(\d{1,4})(?:\s*(?:a|-|–|e|ate)\s*(\d{1,4}))?")
_RE_ARTIGO = re.compile(
    r"\bart(?:igos?|s?\.|º)?\s*(\d{1,3})\s*\.?\s*[ºo°]?\s*(?:-\s*([a-z])\b)?"
    r"(?:\s*(?:,|e|a|-)\s*(\d{1,3})\s*\.?\s*[ºo°]?)?")
_RE_SEGUIMENTO = re.compile(r"\b(seguinte|anterior|proximo|esse|este|desse|deste|nesse|neste|mesmo|isso|"
                            r"ele|ela|artigos?|art)\b")
_RE_ORDINAL = re.compile(
    r"\b\d{1,3}\s*\.?\s*[ºª°]|\b(?:primeir|segund|terceir|quart|quint|sext|penultim|ultim)[oa]s?"
    r"(?=\s+(?:paragrafo|linha|frase|pagina|ponto|numero|alinea))")


def _intervalos(regex, pergunta: str, maximo: int, salto: int) -> list[int]:
    numeros = []
    for m in regex.finditer(normalizar(pergunta)):
        inicio = int(m.group(1))
        fim = int(m.group(2) or inicio)
        if fim < inicio:
            inicio, fim = fim, inicio
        numeros.extend(range(inicio, min(fim, inicio + salto) + 1))
    return list(dict.fromkeys(numeros))[:maximo]


def paginas_mencionadas(pergunta: str) -> list[int]:
    return _intervalos(_RE_PAGINA, pergunta, maximo=3, salto=2)


def artigos_mencionados(pergunta: str) -> list[str]:
    artigos = []
    for m in _RE_ARTIGO.finditer(normalizar(pergunta)):
        inicio, letra, fim = int(m.group(1)), m.group(2), m.group(3)
        if letra:
            artigos.append(f"{inicio}-{letra.upper()}")
            continue
        fim = int(fim) if fim else inicio
        if fim < inicio:
            inicio, fim = fim, inicio
        artigos += [str(n) for n in range(inicio, min(fim, inicio + 3) + 1)]
    return list(dict.fromkeys(artigos))[:4]


def e_seguimento(pergunta: str) -> bool:
    return bool(_RE_SEGUIMENTO.search(normalizar(pergunta)))


def remover_referencias(texto: str) -> str:
    texto = _RE_PAGINA.sub(" ", normalizar(texto))
    texto = _RE_ARTIGO.sub(" ", texto)
    return _RE_ORDINAL.sub(" ", texto)
