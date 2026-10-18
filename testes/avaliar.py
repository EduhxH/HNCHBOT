"""Bateria de perguntas para medir a precisão do chatbot nos documentos reais
(Regulamento Interno e Projeto Educativo do AEHN).

Para cada pergunta verifica:
  - fonte: se a secção/artigo/página certa chegou ao modelo;
  - resposta: se a resposta contém os factos esperados (tirados dos PDFs);
  - só BM25: se a pesquisa por palavras, sem a ajuda da IA, também a encontrava.

Uso:  python testes/avaliar.py            (todas as perguntas, ~12 min por causa
                                           do limite de tokens por minuto da Groq)
      python testes/avaliar.py 1 4 15     (só algumas perguntas)
"""

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

from rag.assistente import (criar_cliente, explicar_erro, modelos_disponiveis,  # noqa: E402
                            modelos_reescrita, recolher_fontes, reescrever, responder)
from rag.indice import Indice, sincronizar  # noqa: E402
from rag.texto import normalizar  # noqa: E402

RI, PE = "regulamento-interno-aehn_2025.pdf", "pe-22_25_vdefinitiva.pdf"


def artigo(numero):
    return lambda f: f["documento"] == RI and f.get("artigo") == numero


def secao(documento, texto):
    return lambda f: f["documento"] == documento and texto.lower() in (f["rotulo"] + f.get("caminho", "")).lower()


def pagina(documento, numero):
    return lambda f: f["documento"] == documento and f["pagina"] <= numero <= f["pagina_fim"]


# (pergunta, fonte esperada, factos que a resposta deve conter, continua a conversa anterior?)
# cada facto pode ser um texto ou um tuplo de alternativas ("dez dias", "10 dias")
PERGUNTAS = [
    ("Quantas faltas injustificadas pode dar um aluno do 1.º ciclo num ano letivo?", artigo("118"), [("dez dias", "10 dias")], False),
    ("O que diz o artigo 120.º?", artigo("120"), ["recuper", "primeira vez"], False),
    ("E o artigo seguinte?", artigo("121"), [], True),
    ("Qual é a composição do Conselho Geral?", artigo("6"), [("vinte e um", "21"), ("oito", "8")], False),
    ("Quanto tempo dura o mandato do diretor?", artigo("17"), [("quatro anos", "4 anos")], False),
    ("Quais são os grupos de recrutamento do departamento de Ciências Experimentais?", artigo("40"),
     ["230", "510", "520"], False),
    ("O que acontece quando um aluno atinge metade do limite de faltas injustificadas?", artigo("118"),
     [("convocad", "convoca")], False),
    ("Quais são as medidas disciplinares sancionatórias?", artigo("128"),
     ["repreensao registada", "transferencia de escola", "expulsao"], False),
    ("Que média precisa um aluno do 4.º ano para receber o diploma de mérito?", artigo("179"), ["4.5"], False),
    ("Os cacifos são gratuitos?", artigo("193"), ["caucao"], False),
    ("Os alunos podem usar o telemóvel nas aulas?", artigo("111"), ["telem"], False),
    ("Que idade têm de ter os representantes dos alunos no Conselho Geral?", artigo("6"), [("16 anos", "dezasseis anos")], False),
    ("O que diz a página 80 do regulamento interno?", pagina(RI, 80), [], False),
    ("Qual é a missão do agrupamento?", secao(PE, "Missão"), ["desenvolvimento integral"], False),
    ("Quais são as metas do eixo 3 do Projeto Educativo?", secao(PE, "EIXO 3"), ["0.5%", "50%", "90%"], False),
    ("Quantos alunos tinha o curso de Técnico de Desporto no 1.º ano em 2021/2022?", pagina(PE, 10), ["28"], False),
    ("Quantas mobilidades Erasmus foram realizadas no total?", pagina(PE, 16), ["131"], False),
    ("Qual foi a taxa de transição no 2.º ano em 2021/2022?", pagina(PE, 12), ["76.4"], False),
    ("O que significa a sigla EMAEI?", lambda f: "emaei" in normalizar(f["texto"]),
     ["equipa multidisciplinar de apoio a educacao inclusiva"], False),
    ("Quando foi criado o agrupamento?", lambda f: "2013" in f["texto"], ["26 de abril de 2013"], False),
    ("Quanto ganha um professor por mês?", None, ["nao encontrei"], False),
    ("Quais são os valores do agrupamento?", secao(PE, "valores"), [], False),
    ("O que significa o 2.º parágrafo da página 5 do Projeto Educativo?", pagina(PE, 5),
     [("articulação", "integração")], False),
]


def _normal(texto: str) -> str:
    """Sem acentos, vírgula decimal como ponto e sem espaços antes de "%" ("0,5 %" -> "0.5%")."""
    texto = re.sub(r"[\s  ]+", " ", normalizar(texto).replace(",", "."))
    return texto.replace(" %", "%")


def main():
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    escolhidas = {int(a) for a in sys.argv[1:]} or set(range(1, len(PERGUNTAS) + 1))
    cliente = criar_cliente().with_options(max_retries=6)  # espera quando o limite por minuto acaba
    disponiveis = modelos_disponiveis(cliente)
    modelo, reescrita = disponiveis[0], modelos_reescrita(disponiveis)
    print(f"modelo: {modelo} | reescrita: {reescrita}")
    indice = Indice(sincronizar(progresso=lambda nome, p, t: print(f"  a ler {nome}: {p}/{t}", flush=True)))

    historico, resultados = [], []
    for n, (pergunta, esperado, factos, continua) in enumerate(PERGUNTAS, start=1):
        if not continua:
            historico = []
        if n not in escolhidas:
            continue
        inicio = time.time()
        plano = reescrever(cliente, reescrita, pergunta, historico, indice)
        fontes = recolher_fontes(indice, pergunta, plano)
        so_bm25 = recolher_fontes(indice, pergunta, {})
        try:
            resposta = "".join(responder(cliente, modelo, pergunta, fontes, historico, plano))
        except Exception as erro:  # mostra o erro e continua com as outras perguntas
            resposta = f"ERRO: {explicar_erro(erro)}"
        fonte_ok = esperado is None or any(esperado(f) for f in fontes)
        bm25_ok = esperado is None or any(esperado(f) for f in so_bm25)
        em_falta = [f for f in factos
                    if not any(_normal(x) in _normal(resposta) for x in (f if isinstance(f, tuple) else (f,)))]
        resultados.append((n, fonte_ok, not em_falta, bm25_ok))

        print("=" * 100)
        print(f"{n}. {pergunta}")
        print(f"   plano: grupos={plano.get('grupos')} artigos={plano.get('artigos')} "
              f"palavras={plano.get('palavras_chave')}")
        print("   fontes: " + " | ".join(f"{f['rotulo'][:45]} p.{f['pagina']}" for f in fontes))
        print(f"   FONTE {'OK' if fonte_ok else 'FALHOU'} | RESPOSTA {'OK' if not em_falta else 'FALTA ' + str(em_falta)}"
              f" | só BM25 {'OK' if bm25_ok else 'falhava'} | {time.time() - inicio:.1f}s")
        print("   " + resposta.replace("\n", "\n   ")[:1500])
        historico += [{"papel": "user", "conteudo": pergunta}, {"papel": "assistant", "conteudo": resposta}]
        time.sleep(max(0.0, 30 - (time.time() - inicio)))  # respeita os 8000 tokens/minuto

    total = len(resultados)
    print("=" * 100)
    print(f"fontes certas: {sum(r[1] for r in resultados)}/{total} | respostas certas: "
          f"{sum(r[2] for r in resultados)}/{total} | só BM25: {sum(r[3] for r in resultados)}/{total}")
    print("falharam:", [r[0] for r in resultados if not (r[1] and r[2])])


if __name__ == "__main__":
    main()
