import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymupdf  # noqa: E402

from rag.pdfs import _linha_ocr_valida, extrair_documento, imagem_pagina  # noqa: E402
from rag.texto import normalizar  # noqa: E402

A4 = pymupdf.paper_rect("a4")


def imagem_de_texto(texto: str, largura: float, altura: float, tamanho: float = 13, dpi: int = 150) -> bytes:
    rascunho = pymupdf.open()
    pagina = rascunho.new_page(width=largura, height=altura)
    pagina.draw_rect(pagina.rect, color=(0.2, 0.2, 0.2), fill=(1, 1, 0.92), width=1.5)
    pagina.insert_textbox(pagina.rect + (12, 12, -12, -12), texto, fontname="helv", fontsize=tamanho)
    return pagina.get_pixmap(dpi=dpi).tobytes("png")


def imagem_de_grafico() -> bytes:
    rascunho = pymupdf.open()
    pagina = rascunho.new_page(width=420, height=260)
    pagina.insert_text((20, 30), "Taxa de sucesso escolar por ano", fontname="helv", fontsize=14)
    for i, (ano, valor) in enumerate([("2021", 82), ("2022", 87), ("2023", 91)]):
        x, topo = 60 + i * 120, 220 - valor * 1.6
        pagina.draw_rect(pymupdf.Rect(x, topo, x + 70, 220), color=None, fill=(0.2, 0.4, 0.8))
        pagina.insert_text((x + 18, topo - 6), f"{valor}%", fontname="helv", fontsize=12)
        pagina.insert_text((x + 20, 240), ano, fontname="helv", fontsize=12)
    return pagina.get_pixmap(dpi=150).tobytes("png")


def imagem_de_botao(texto: str) -> bytes:
    rascunho = pymupdf.open()
    pagina = rascunho.new_page(width=110, height=18)
    pagina.draw_rect(pagina.rect + (1, 1, -1, -1), color=(0.45, 0.45, 0.45), fill=(0.94, 0.94, 0.94))
    pagina.insert_text((9, 12.5), texto, fontname="helv", fontsize=9)
    return pagina.get_pixmap(dpi=200).tobytes("png")


def aviso_em_imagem(doc):
    pagina = doc.new_page(width=A4.width, height=A4.height)
    pagina.insert_textbox(pymupdf.Rect(60, 60, 535, 200), "Informações da visita de estudo. Este parágrafo está "
                          "na camada de texto do PDF.", fontname="helv", fontsize=12)
    pagina.insert_image(pymupdf.Rect(60, 210, 535, 330), stream=imagem_de_texto(
        "Aviso afixado: o prazo de inscrição na visita de estudo termina a 15 de março. Custo por aluno: 12 euros.",
        475, 120))


def digitalizado(doc):
    for texto in ["Ata da reunião geral de pais. A reunião geral de pais realiza-se no auditório às 18h30 do dia "
                  "4 de novembro. Ordem de trabalhos: 1) apresentação do diretor de turma; 2) calendário das "
                  "avaliações; 3) visitas de estudo.",
                  "Deliberações: foi aprovado por unanimidade o plano de atividades do primeiro período. "
                  "A próxima reunião fica marcada para 20 de janeiro."]:
        pagina = doc.new_page(width=A4.width, height=A4.height)
        pagina.insert_image(pagina.rect, stream=imagem_de_texto(texto, A4.width, A4.height, tamanho=14, dpi=200))


def grafico_em_imagem(doc):
    pagina = doc.new_page(width=A4.width, height=A4.height)
    pagina.insert_textbox(pymupdf.Rect(60, 60, 535, 120), "Resultados escolares. O gráfico seguinte mostra a evolução.",
                          fontname="helv", fontsize=12)
    pagina.insert_image(pymupdf.Rect(80, 130, 500, 390), stream=imagem_de_grafico())


def esquema_vetorial(doc):
    pagina = doc.new_page(width=A4.width, height=A4.height)
    caixas = {"Diretor": (230, 80), "Conselho Pedagógico": (90, 200), "Conselho Geral": (370, 200),
              "Departamentos Curriculares": (90, 320)}
    for nome, (x, y) in caixas.items():
        caixa = pymupdf.Rect(x, y, x + 150, y + 50)
        pagina.draw_rect(caixa, color=(0, 0, 0), fill=(0.9, 0.95, 1))
        pagina.insert_textbox(caixa + (5, 15, -5, 0), nome, fontname="helv", fontsize=10, align=1)
    for inicio, fim in [((305, 130), (165, 200)), ((305, 130), (445, 200)), ((165, 250), (165, 320))]:
        pagina.draw_line(inicio, fim)


def botao_numa_frase(doc):
    pagina = doc.new_page(width=A4.width, height=A4.height)
    pagina.insert_textbox(pymupdf.Rect(60, 60, 535, 110), "A convocatória pode ser enviada por correio eletrónico aos "
                          "encarregados de educação dos alunos assinalados na coluna Email.", fontname="helv", fontsize=11)
    inicio = "Para isso, clique no botão"
    x = 60 + pymupdf.get_text_length(inicio, fontsize=11) + 4
    pagina.insert_text((60, 128), inicio, fontname="helv", fontsize=11)
    pagina.insert_image(pymupdf.Rect(x, 117, x + 110, 135), stream=imagem_de_botao("Enviar convocatória"))
    pagina.insert_text((x + 116, 128), "depois de feita a seleção.", fontname="helv", fontsize=11)


def captura_numa_pagina_com_texto(doc):
    pagina = doc.new_page(width=A4.width, height=A4.height)
    pagina.insert_textbox(pymupdf.Rect(60, 60, 535, 260), " ".join(["A ficha do aluno reúne os dados de identificação, "
                          "a turma e os contactos do encarregado de educação."] * 5), fontname="helv", fontsize=11)
    pagina.insert_image(pymupdf.Rect(60, 270, 400, 380), stream=imagem_de_texto(
        "Ficha do aluno\nNome: Ana Sousa\nTurma: 7.º A\nEncarregado de educação: Rui Sousa", 340, 110, tamanho=11))


def logotipo_repetido(doc):
    logotipo = None
    for texto in ["O primeiro capítulo apresenta a plataforma e explica como entrar com o utilizador e a palavra-passe "
                  "fornecidos pela escola no início do ano letivo.",
                  "O segundo capítulo mostra como registar os sumários das aulas, incluindo as faltas dos alunos e os "
                  "materiais usados em cada lição.",
                  "O terceiro capítulo descreve as reuniões com os encarregados de educação e a forma de enviar as "
                  "convocatórias por correio eletrónico."]:
        pagina = doc.new_page(width=A4.width, height=A4.height)
        caixa = pymupdf.Rect(60, 30, 260, 70)
        if logotipo is None:
            logotipo = pagina.insert_image(caixa, stream=imagem_de_texto("ESCOLA MODELO", 200, 40, tamanho=16))
        else:
            pagina.insert_image(caixa, xref=logotipo)
        pagina.insert_textbox(pymupdf.Rect(60, 90, 535, 200), texto, fontname="helv", fontsize=11)


CASOS = [
    ("aviso em imagem numa página com texto", aviso_em_imagem,
     ["camada de texto do PDF", "prazo de inscrição na visita de estudo", "12 euros"], [], None),
    ("documento digitalizado", digitalizado,
     ["reunião geral de pais realiza-se no auditório", "aprovado por unanimidade"], [],
     "reunião geral de pais realiza-se no auditório"),
    ("gráfico em imagem", grafico_em_imagem,
     ["O gráfico seguinte mostra a evolução", "Taxa de sucesso escolar"], [], None),
    ("esquema desenhado com texto", esquema_vetorial, ["Conselho Pedagógico", "Departamentos Curriculares"], [], None),
    ("botão em imagem no meio de uma frase", botao_numa_frase, ["clique no botão", "Enviar convocatória"], [], None),
    ("captura de ecrã numa página com muito texto", captura_numa_pagina_com_texto,
     ["contactos do encarregado de educação", "Ana Sousa", "Rui Sousa"], [], None),
    ("logótipo repetido em todas as páginas", logotipo_repetido,
     ["registar os sumários das aulas", "reuniões com os encarregados de educação"], ["ESCOLA MODELO"], None),
]

LINHAS_OCR = [
    ("Aviso afixado: o prazo de inscrição na visita de estudo termina a 15 de março.", True),
    ("Custo por aluno: 12 euros.", True),
    ("Oferta formativa diversificada", True),
    ("DESAFIAR A ESCOLA", True),
    ("91%", True),
    ("às 18h30 do dia 4", True),
    ("oO ronm", False),
    ("[Ei ooNesORA o,", False),
    ("1 4r4 Re er", False),
    ("Sabe Tor RCoralização Us", False),
    ("o aprender a", True),
    ("e o", None),
    (": |", None),
]


def main():
    falhas = 0
    with tempfile.TemporaryDirectory() as pasta:
        for nome, construir, frases, proibidas, destacar in CASOS:
            caminho = Path(pasta) / f"{construir.__name__}.pdf"
            doc = pymupdf.open()
            construir(doc)
            doc.save(caminho, deflate=True)
            lido = extrair_documento(caminho)
            texto = normalizar("\n".join(e["texto"] for e in lido["elementos"]))
            em_falta = [f"não leu «{f}»" for f in frases if normalizar(f) not in texto]
            em_falta += [f"leu «{f}», que devia ser ignorado" for f in proibidas if normalizar(f) in texto]
            if destacar and imagem_pagina(caminho, 1, destacar, ocr=True) == imagem_pagina(caminho, 1, destacar):
                em_falta.append(f"«Ver no PDF» não destacou «{destacar}»")
            falhas += bool(em_falta)
            ocr = f"OCR nas páginas {lido['paginas_ocr']}" if lido["paginas_ocr"] else "sem OCR"
            print(f"{'OK    ' if not em_falta else 'FALHOU'} {nome} ({ocr})"
                  + "".join(f"\n       {falha}" for falha in em_falta), flush=True)
    erradas = [linha for linha, esperado in LINHAS_OCR if _linha_ocr_valida(linha.split()) != esperado]
    falhas += bool(erradas)
    print(f"{'OK    ' if not erradas else 'FALHOU'} filtro das linhas lidas por OCR "
          f"({len(LINHAS_OCR) - len(erradas)}/{len(LINHAS_OCR)} decisões certas)"
          + "".join(f"\n       decisão errada: «{linha}»" for linha in erradas))
    print(f"{len(CASOS) + 1 - falhas}/{len(CASOS) + 1} casos certos")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
