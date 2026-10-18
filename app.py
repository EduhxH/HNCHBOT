"""Assistente de Físico-Química: perguntas sobre vários PDFs (Streamlit + Groq).

Executar:  streamlit run app.py
"""

import os
import re
from pathlib import Path

import groq
import streamlit as st
from dotenv import load_dotenv

from rag.assistente import (MODELOS_PREFERIDOS, criar_cliente, explicar_erro, modelo_reescrita,
                            modelos_disponiveis, recolher_fontes, reescrever, responder)
from rag.indice import PASTA_DOCUMENTOS, Indice, assinatura_pasta, sincronizar
from rag.pdfs import imagem_pagina

load_dotenv()
st.set_page_config(page_title="Assistente de FQ", page_icon="⚛️", layout="wide")


@st.cache_resource(show_spinner="A ler os PDFs (só demora na primeira vez)...", max_entries=2)
def carregar_indice(assinatura: tuple) -> Indice:
    # `assinatura` muda quando um PDF é adicionado/alterado, o que refaz o índice
    return Indice(sincronizar())


@st.cache_data(show_spinner=False, ttl=3600)
def listar_modelos(chave: str) -> list[str]:
    return modelos_disponiveis(criar_cliente(chave))


@st.cache_data(show_spinner=False, max_entries=50)
def desenhar_pagina(caminho: str, pagina: int, destacar: str) -> bytes:
    return imagem_pagina(caminho, pagina, destacar)


def escapar(texto: str) -> str:
    """Evita que símbolos do PDF ($, *, _, ...) sejam interpretados como Markdown."""
    return re.sub(r"([\\`*_{}\[\]<>#+!|$~])", r"\\\1", texto)


@st.dialog("Página do PDF", width="large")
def ver_pagina(fonte: dict, indice: Indice):
    st.markdown(f"**{escapar(fonte['documento'])}** — página {fonte['pagina']}")
    caminho = indice.caminho(fonte["documento"])
    if not caminho.exists():
        st.warning("Este PDF já não está na pasta documentos/.")
        return
    if fonte["tipo"] == "trecho":
        st.caption("O trecho usado na resposta está destacado a amarelo.")
    destacar = fonte["texto"] if fonte["tipo"] == "trecho" else ""
    st.image(desenhar_pagina(str(caminho), fonte["pagina"], destacar), width="stretch")


def mostrar_fontes(fontes: list[dict], chave: int, indice: Indice):
    if not fontes:
        return
    with st.expander(f"📄 Fontes ({len(fontes)})"):
        for n, fonte in enumerate(fontes, start=1):
            tipo = "página completa" if fonte["tipo"] == "pagina" else "trecho"
            st.markdown(f"**[{n}] {escapar(fonte['documento'])}** — página {fonte['pagina']} · *{tipo}*")
            texto = fonte["texto"] if len(fonte["texto"]) <= 600 else fonte["texto"][:600] + "…"
            st.caption(escapar(texto).replace("\n", "  \n"))
            if st.button("🔍 Ver página no PDF", key=f"ver-{chave}-{n}"):
                ver_pagina(fonte, indice)
            if n < len(fontes):
                st.divider()


st.session_state.setdefault("mensagens", [])
st.session_state.setdefault("envio", 0)

# ---------------------------------------------------------------- barra lateral
with st.sidebar:
    st.header("📚 Documentos")
    enviados = st.file_uploader("Adicionar PDFs", type="pdf", accept_multiple_files=True,
                                key=f"envio-{st.session_state.envio}")
    if enviados:
        PASTA_DOCUMENTOS.mkdir(exist_ok=True)
        for ficheiro in enviados:
            (PASTA_DOCUMENTOS / Path(ficheiro.name).name).write_bytes(ficheiro.getbuffer())
        st.session_state.envio += 1  # limpa o campo de envio
        st.rerun()

    indice = carregar_indice(assinatura_pasta())
    nomes = indice.nomes()
    total_paginas = sum(indice.num_paginas(n) for n in nomes)

    with st.expander(f"{len(nomes)} PDF(s) · {total_paginas} páginas", expanded=len(nomes) <= 8):
        if not nomes:
            st.write("Ainda não há PDFs. Adiciona-os acima ou copia-os para a pasta `documentos/`.")
        for nome in nomes:
            doc = indice.documentos[nome]
            paginas = len(doc["paginas"])
            caracteres = sum(len(p) for pag in doc["paginas"] for p in pag)
            if doc["erro"]:
                st.error(f"**{nome}**: não foi possível ler ({doc['erro']})")
            elif caracteres < 30 * max(paginas, 1):
                st.warning(f"**{nome}**: quase sem texto. Será um PDF digitalizado (imagem)? Precisa de OCR.")
            else:
                st.markdown(f"- {escapar(nome)} · {paginas} pág.")

    filtro = st.multiselect("Pesquisar só em", nomes, placeholder="Todos os documentos")

    st.header("⚙️ Definições")
    chave_manual = st.text_input("Chave da API Groq", type="password",
                                 help="Não é preciso se já estiver no ficheiro .env")
    cliente = criar_cliente(chave_manual or None)
    if cliente:
        st.caption("✅ Chave da Groq configurada")
    else:
        st.caption("⚠️ Sem chave da Groq: só são mostrados os trechos encontrados.")

    modelos = listar_modelos(chave_manual or os.getenv("GROQ_API_KEY", "")) if cliente else MODELOS_PREFERIDOS
    modelo_padrao = os.getenv("GROQ_MODELO")
    modelo = st.selectbox("Modelo", modelos,
                          index=modelos.index(modelo_padrao) if modelo_padrao in modelos else 0)
    k = st.slider("Trechos por pergunta", 3, 10, 6)
    temperatura = st.slider("Criatividade (temperatura)", 0.0, 1.0, 0.2, 0.1)
    if st.button("🗑️ Limpar conversa", width="stretch"):
        st.session_state.mensagens = []
        st.rerun()

# ---------------------------------------------------------------- conversa
st.title("⚛️ Assistente de Físico-Química")
st.caption("Faz perguntas sobre os PDFs: conceitos, trechos ou *«o que significa o 2.º parágrafo "
           "da página 3?»*. Cada resposta indica o documento e a página de onde veio.")

for i, mensagem in enumerate(st.session_state.mensagens):
    with st.chat_message(mensagem["papel"]):
        st.markdown(mensagem["conteudo"])
        mostrar_fontes(mensagem.get("fontes", []), i, indice)

caixa_exemplos, exemplo = st.empty(), None
if not st.session_state.mensagens and nomes:
    with caixa_exemplos.container():
        st.write("Experimenta:")
        exemplos = [f"Explica o 2.º parágrafo da página 1 de «{Path(nomes[0]).stem}»",
                    "O que diz a Lei de Lavoisier?",
                    "Quais são as três Leis de Newton?"]
        for coluna, texto in zip(st.columns(len(exemplos)), exemplos):
            if coluna.button(texto, width="stretch"):
                exemplo = texto

pergunta = st.chat_input("Escreve a tua pergunta...") or exemplo
if pergunta:
    caixa_exemplos.empty()
    historico = st.session_state.mensagens
    with st.chat_message("user"):
        st.markdown(pergunta)

    with st.chat_message("assistant"):
        with st.status("A procurar nos documentos...") as estado:
            plano = (reescrever(cliente, modelo_reescrita(modelos), pergunta, historico, indice)
                     if cliente else {})
            fontes = recolher_fontes(indice, pergunta, plano, k=k, filtro=filtro or None)
            estado.update(label=f"Encontrei {len(fontes)} fonte(s)", state="complete", expanded=False)

        if not fontes:
            resposta = "Não encontrei nada sobre isso nos documentos. Tenta outras palavras ou indica o documento/página."
            st.markdown(resposta)
        elif not cliente:
            resposta = ("⚠️ **Sem chave da Groq** não consigo escrever uma resposta, "
                        "mas estes são os trechos mais relevantes que encontrei (abre as fontes).")
            st.markdown(resposta)
        else:
            try:
                resposta = st.write_stream(
                    responder(cliente, modelo, pergunta, fontes, historico, plano, temperatura))
                if not isinstance(resposta, str):
                    resposta = "".join(map(str, resposta))
            except groq.APIError as erro:
                resposta = f"⚠️ {explicar_erro(erro)}"
                st.markdown(resposta)
        mostrar_fontes(fontes, len(historico) + 1, indice)

    st.session_state.mensagens = historico + [
        {"papel": "user", "conteudo": pergunta},
        {"papel": "assistant", "conteudo": resposta, "fontes": fontes},
    ]
    st.rerun()  # volta a desenhar a conversa a partir do histórico (estrutura estável)
