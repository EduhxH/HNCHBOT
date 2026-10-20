"""Bateria de perguntas para medir a precisão do chatbot nos documentos reais
(Regulamento Interno e Projeto Educativo do AEHN).

Para cada pergunta verifica:
  - fonte: se a secção/artigo/página certa chegou ao modelo;
  - resposta: se a resposta contém os factos esperados (tirados dos PDFs);
  - só BM25: se a pesquisa por palavras, sem a ajuda da IA, também a encontrava;
  - citações: se o texto que a resposta cita (entre aspas ou em linhas "> ...") existe nas fontes.

Uso:  python testes/avaliar.py            (todas as perguntas, ~35 min por causa
                                           do limite de tokens por minuto da Groq;
                                           gasta quase todo o limite diário do plano gratuito)
      python testes/avaliar.py 1 4 15     (só algumas perguntas)
"""

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

from rag.assistente import (citacoes, criar_cliente, explicar_erro, modelos_disponiveis,  # noqa: E402
                            modelos_reescrita, recolher_fontes, reescrever, responder, verificar_citacoes)
from rag.indice import RAIZ, Indice, sincronizar  # noqa: E402
from rag.texto import normalizar  # noqa: E402

RI, PE = "regulamento-interno-aehn_2025.pdf", "pe-22_25_vdefinitiva.pdf"
# respostas completas, fontes e citações de cada pergunta (o terminal só mostra o início)
FICHEIRO_RESULTADOS = RAIZ / "dados" / "avaliacao.json"


def artigo(numero):
    return lambda f: f["documento"] == RI and f.get("artigo") == numero


def secao(documento, texto):
    return lambda f: f["documento"] == documento and texto.lower() in (f["rotulo"] + f.get("caminho", "")).lower()


def pagina(documento, numero):
    return lambda f: f["documento"] == documento and f["pagina"] <= numero <= f["pagina_fim"]


def algum(*testes):
    return lambda f: any(t(f) for t in testes)


# (pergunta, fonte esperada, factos que a resposta deve conter, continua a conversa anterior?)
# a fonte esperada pode ser um tuplo: todas essas fontes têm de chegar ao modelo
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

    # ---- palavras diferentes das do texto (sinónimos, linguagem do dia a dia)
    ("Quem fica no lugar do diretor quando ele está ausente?", artigo("14"), ["subdiretor"], False),
    ("Até quando posso justificar uma falta do meu educando?", artigo("116"),
     [("3.º dia util", "3º dia util", "terceiro dia util")], False),
    ("Chegar atrasado às aulas várias vezes dá falta?", artigo("114"), ["terceira"], False),
    ("Há regras sobre a roupa que os alunos podem usar na escola?", artigo("111"), ["vestuario"], False),
    ("Os alunos podem fumar à entrada da escola?", artigo("111"),
     [("espacos de acesso", "acesso as instalacoes")], False),
    ("Quantos alunos pode ter uma turma do 5.º ano?", artigo("181"), ["24", "28"], False),
    ("Quanto tempo podem durar as reuniões dos professores?", artigo("183"),
     [("duas horas", "2 horas"), ("meia hora", "30 minutos")], False),
    ("Quantas vezes pode um manual escolar ser reutilizado?", artigo("189"),
     [("tres reutilizacoes", "3 reutilizacoes", "tres vezes", "3 vezes")], False),
    ("O que acontece se não devolver os manuais escolares no fim do ano?", artigo("186"), ["valor de capa"], False),
    ("O meu filho pode sair da escola à hora de almoço?", artigo("196"), ["autorizacao parcial"], False),
    ("Quem decide se um aluno é transferido de escola?", artigo("128"),
     [("diretor-geral da educacao", "diretor geral da educacao")], False),
    ("A partir de que idade um aluno pode ser transferido de escola como castigo?", artigo("128"),
     [("10 anos", "dez anos")], False),
    ("Que peso tem a componente científica e pedagógica na avaliação dos professores?", artigo("232"),
     ["60%"], False),
    ("De quanto tempo dispõe o diretor de turma por semana para receber os pais?", artigo("240"),
     ["50 minutos"], False),
    ("O que acontece a um aluno que insiste em usar o telemóvel nas aulas?", artigo("111"),
     ["repreensao registada", ("um dia de suspensao", "1 dia de suspensao")], False),
    # o preço não está no texto: a resposta deve remeter para a tabela, sem inventar um valor
    ("Quanto custa a segunda via do cartão da escola?", artigo("192"), ["tabela"], False),

    # ---- respostas que juntam 2 ou 3 artigos (ou os dois documentos)
    ("Qual é a diferença entre medidas corretivas e sancionatórias? Dá exemplos de cada.",
     (artigo("126"), artigo("128")), ["advertencia", "repreensao registada"], False),
    ("Quanto tempo duram os mandatos do diretor e dos membros do Conselho Geral?",
     (artigo("17"), artigo("10")), [("quatro anos", "4 anos"), ("dois anos", "2 anos")], False),
    ("Quem faz parte do Conselho Pedagógico e quanto tempo dura o mandato dos seus membros?",
     (artigo("24"), artigo("25")), ["17", ("quatro anos", "4 anos")], False),
    ("Quando é que uma falta é injustificada e quantas pode dar um aluno do 1.º ciclo?",
     (artigo("117"), artigo("118")), ["fora do prazo", ("dez dias", "10 dias")], False),
    ("Quem aprova o Projeto Educativo e quando foi aprovado?", pagina(PE, 24),
     ["conselho geral", "2 de maio de 2023"], False),

    # ---- tabelas do Projeto Educativo (linha e coluna certas)
    ("Quantos alunos estavam inscritos em Línguas e Humanidades no 10.º ano?", pagina(PE, 10), ["108"], False),
    ("Quantos alunos com medidas seletivas e adicionais havia no 3.º ciclo?", pagina(PE, 11), ["52"], False),
    ("Quantos alunos tinham escalão A da ação social escolar?", pagina(PE, 11), ["153"], False),
    ("Qual foi a taxa de transição no 2.º ano dos cursos profissionais?", pagina(PE, 12), ["61.5"], False),
    ("Quantos professores contratados havia no agrupamento?", secao(PE, "Pessoal docente"), ["32"], False),
    ("Qual foi a taxa de adesão dos professores ao programa Escola Digital?", pagina(PE, 15), ["53%"], False),
    ("Qual é a meta de sucesso para os alunos com PLNM?", secao(PE, "EIXO 3"), ["90%"], False),
    ("Que percentagem das salas de aula deve ter equipamentos digitais?", secao(PE, "EIXO 2"), ["90%"], False),
    ("Qual é a população residente na freguesia do Ramalhal?", pagina(PE, 8), [("3 631", "3631", "3.631")], False),
    ("Quantas mobilidades Erasmus foram recebidas pelo agrupamento?", pagina(PE, 16), ["106"], False),

    # ---- perguntas de seguimento ("e o 9.º?", "o mandato dele")
    ("Quantos alunos tinha o 7.º ano em 2021/2022?", pagina(PE, 10), ["79"], False),
    ("E o 9.º?", pagina(PE, 10), ["93"], True),
    ("Quem elege o diretor?", algum(artigo("15"), artigo("7")), ["conselho geral"], False),
    ("E quanto tempo dura o mandato dele?", artigo("17"), [("quatro anos", "4 anos")], True),
    ("Pode ser reconduzido para um terceiro mandato seguido?", artigo("17"),
     ["terceiro mandato", ("nao e permitid", "nao sendo permitid", "nao pode", "nao permite")], True),

    # ---- sem resposta nos documentos
    ("Qual é o valor da propina dos cursos profissionais?", None, ["nao encontrei"], False),
    ("Quantos dias de férias têm os professores por ano?", None, ["nao encontrei"], False),
    ("Qual é o número de telefone da escola sede?", None, ["nao encontrei"], False),
]


def _encontrada(esperado, fontes: list[dict]) -> bool:
    testes = esperado if isinstance(esperado, tuple) else (esperado,)
    return all(any(teste(f) for f in fontes) for teste in testes if teste)


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

    historico, resultados, completos = [], [], []
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
            if "per day" in str(erro):  # limite diário: as perguntas seguintes falhariam todas
                print(f"{n}. {pergunta}\n   {resposta}\n   A bateria parou aqui.")
                break
        fonte_ok = _encontrada(esperado, fontes)
        bm25_ok = _encontrada(esperado, so_bm25)
        em_falta = [f for f in factos
                    if not any(_normal(x) in _normal(resposta) for x in (f if isinstance(f, tuple) else (f,)))]
        verificadas = len(citacoes(resposta))
        nao_encontradas = verificar_citacoes(resposta, fontes, historico, pergunta)
        resultados.append((n, fonte_ok, not em_falta, bm25_ok, verificadas, len(nao_encontradas)))

        print("=" * 100)
        print(f"{n}. {pergunta}")
        print(f"   plano ({plano.get('modelo', 'sem plano')}): grupos={plano.get('grupos')} "
              f"artigos={plano.get('artigos')} palavras={plano.get('palavras_chave')}")
        print("   fontes: " + " | ".join(f"{f['rotulo'][:45]} p.{f['pagina']}" for f in fontes))
        print(f"   FONTE {'OK' if fonte_ok else 'FALHOU'} | RESPOSTA {'OK' if not em_falta else 'FALTA ' + str(em_falta)}"
              f" | só BM25 {'OK' if bm25_ok else 'falhava'} | citações {verificadas - len(nao_encontradas)}/"
              f"{verificadas} nas fontes | {time.time() - inicio:.1f}s")
        for citacao in nao_encontradas:
            print(f"   CITAÇÃO NÃO ENCONTRADA: «{citacao[:300]}»")
        print("   " + resposta.replace("\n", "\n   ")[:1500])
        completos.append({"n": n, "pergunta": pergunta, "continua": continua, "plano": plano, "fontes": fontes,
                          "resposta": resposta, "fonte_ok": fonte_ok, "factos_em_falta": em_falta,
                          "citacoes_em_falta": nao_encontradas})
        FICHEIRO_RESULTADOS.write_text(json.dumps(completos, ensure_ascii=False, indent=1), encoding="utf-8")
        historico += [{"papel": "user", "conteudo": pergunta},
                      {"papel": "assistant", "conteudo": resposta, "fontes": fontes}]
        time.sleep(max(0.0, 30 - (time.time() - inicio)))  # respeita os 8000 tokens/minuto

    total = len(resultados)
    print("=" * 100)
    print(f"fontes certas: {sum(r[1] for r in resultados)}/{total} | respostas certas: "
          f"{sum(r[2] for r in resultados)}/{total} | só BM25: {sum(r[3] for r in resultados)}/{total}")
    print(f"citações verificadas: {sum(r[4] for r in resultados)} | não encontradas nas fontes: "
          f"{sum(r[5] for r in resultados)} (perguntas {[r[0] for r in resultados if r[5]]})")
    print("falharam:", [r[0] for r in resultados if not (r[1] and r[2])])


if __name__ == "__main__":
    main()
