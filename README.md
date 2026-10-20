# 📚 Assistente de documentos — chatbot para PDFs com a Groq

Demo de um chatbot que **só responde com base nos PDFs** da pasta `documentos/`, feito para
consultar o **Regulamento Interno** e o **Projeto Educativo** do Agrupamento de Escolas Henriques Nogueira
(funciona com outros PDFs). Exemplos de perguntas:

- *"Quantas faltas injustificadas pode dar um aluno do 1.º ciclo?"*
- *"O que diz o artigo 120.º?"* → e a seguir *"E o artigo seguinte?"*
- *"Quais são as metas do eixo 3 do Projeto Educativo?"*
- *"Quantos alunos tinha o curso de Técnico de Desporto no 1.º ano?"* (lido de uma tabela)
- *"O que diz a página 80 do regulamento?"*

Cada resposta cita a fonte (`[1]`, e no regulamento também *artigo, n.º e alínea*). Em **Fontes** vê-se
de que documento, capítulo, artigo e página veio cada trecho. O botão **🔍 Ver no PDF** mostra a página
original com o trecho destacado a amarelo.

Usa a API da [Groq](https://console.groq.com) e uma interface em [Streamlit](https://streamlit.io).

---

## Como lê os documentos

Para responder com precisão, o mais importante é ler bem os PDFs. Cada PDF é lido uma vez
(cerca de 1 minuto para 160 páginas) e o resultado fica guardado em `dados/indice.json`:

1. **Texto e layout** — o [`pymupdf4llm`](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/) com
   o `pymupdf-layout` junta as linhas em parágrafos e reconhece títulos, listas (pontos `1 —`,
   alíneas `a)`) e tabelas.
2. **Tabelas** — se uma tabela sai com palavras partidas entre células (ex.: tabelas com cabeçalhos
   na vertical ou células fundidas), é trocada pela leitura da grelha da própria tabela. As células
   fundidas na vertical repetem o rótulo (ex.: "1.º Ciclo" em cada ano).
3. **Limpeza** — retira cabeçalhos/rodapés repetidos ("Regulamento Interno AEHN · Página 80 de 160"),
   as páginas de índice, palavras coladas ("residenteporgrandesgrupos") e junta títulos e
   parágrafos partidos pelo fim da linha ou da página.
4. **Estrutura** — o regulamento fica dividido em **artigos** (todos os 274, incluindo o 58.º-A e o
   58.º-B), cada um com o capítulo, secção e subsecção a que pertence. O Projeto Educativo fica
   dividido pelos seus títulos.
5. **Verificação** — compara as palavras lidas com as do PDF e avisa (na barra lateral e no
   `indexar.py`) se alguma página ficou incompleta.

## Como responde

```
pergunta ──► Groq (modelo pequeno) reescreve a pergunta, sugere palavras-chave como estariam
             escritas no documento e escolhe capítulos/secções num MAPA dos documentos
                                   │
                                   ▼
            fontes: artigo/página pedidos ("artigo 120.º", "página 80") vão inteiros
                    + pesquisa BM25 nos trechos, com bónus para as secções escolhidas
                                   │
                                   ▼
            Groq (modelo grande) responde SÓ com essas fontes, cita [n], artigo, n.º e alínea
                                   │
                                   ▼
            verificação: o texto entre aspas na resposta tem de existir nas fontes;
            se não existir, aparece um aviso por baixo da resposta
```

- A Groq não tem modelos de *embeddings*. Por isso a pesquisa é por palavras (BM25, adaptado ao
  português) e a parte "por significado" vem da IA, que escolhe as secções a partir do mapa.
- O mapa tem só capítulos, secções e intervalos de artigos (~2 200 tokens). O índice completo dos
  274 artigos gastaria demasiado do limite do plano gratuito (8 000 tokens por minuto por modelo).
- A verificação das citações (“...”, «...», "...") ignora maiúsculas, acentos, pontuação, markdown
  e marcadores como "a)" ou "1 —", e aceita omissões marcadas com "(…)". Citações com menos de 3
  palavras (termos como "Kit Digital") não são verificadas. A resposta nunca é bloqueada: o aviso
  só diz ao professor para confirmar aquela frase no PDF.
- Os modelos são pedidos à Groq quando o chatbot abre (os Llama já foram retirados). Por defeito
  responde o `openai/gpt-oss-120b` e prepara a pesquisa o `openai/gpt-oss-20b` (ou o `qwen`, se o
  limite do primeiro acabar).

## Instalação

### Opção rápida (Windows)

1. Instalar o [Python](https://www.python.org/downloads/) (3.10 ou superior).
2. Fazer duplo clique em **`iniciar.bat`**. Da primeira vez, cria o ambiente e instala tudo.
3. Abrir o ficheiro `.env` que foi criado e colocar a chave da Groq (ver abaixo).
4. O chatbot abre no browser em http://localhost:8501

### Opção manual

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # Linux/Mac: cp .env.example .env
python indexar.py               # opcional: lê os PDFs mostrando o progresso
streamlit run app.py
```

### Chave da Groq

1. Criar conta em https://console.groq.com e gerar uma chave em **API Keys**. O plano gratuito chega para a demo.
2. Colocá-la no ficheiro `.env`:
   ```
   GROQ_API_KEY=gsk_...
   ```
   Também se pode colar na barra lateral do chatbot, no campo *Chave da API Groq*.

Sem chave, o chatbot continua a funcionar em modo de pesquisa: mostra os trechos e páginas
encontrados, mas não escreve respostas.

## Documentos

Os PDFs ficam em **`documentos/`** (podem estar em subpastas) ou são arrastados para o campo
**Adicionar PDFs** na barra lateral. Não vão para o repositório git.

Para testar sem os documentos reais, `python exemplos/gerar_pdfs_exemplo.py` cria 3 PDFs de exemplo
de Físico-Química.

## Testes de precisão

`testes/avaliar.py` faz 62 perguntas aos documentos reais: as 23 iniciais e mais perguntas com
palavras diferentes das do texto ("roupa" → "vestuário", "castigo" → "medida disciplinar"), que
juntam 2 ou 3 artigos, sobre tabelas do Projeto Educativo, de seguimento ("E o 9.º?") e sem resposta
nos documentos. Para cada uma verifica:
- se a fonte certa (artigo, secção ou página) chegou ao modelo;
- se a resposta tem os factos certos, tirados dos PDFs (ex.: "dez dias", "caução", "76,4");
- se a pesquisa só por palavras, sem a IA, também a encontrava;
- se o texto citado na resposta (entre aspas ou em linhas "> ...") existe nas fontes.

```bash
python testes/avaliar.py          # todas (~35 min, por causa do limite por minuto da Groq)
python testes/avaliar.py 1 2 3    # só algumas
```

As respostas completas, as fontes e as citações não encontradas ficam em `dados/avaliacao.json`.

Resultados (20/10/2026): na primeira volta completa, 56/62 respostas certas (as 23 iniciais todas
certas). As 6 falhas eram de recolha de fontes ou de respostas incompletas; depois das correções às
instruções, 5 passaram a certas e as perguntas 1–14 continuaram 14/14 (a volta parou aí por causa do
limite diário da Groq). Continua a falhar a 38 (o telemóvel: a sanção está no n.º 6 do artigo 111.º,
que só remete para a "alínea r)" e não diz "telemóvel"). Das 45 citações verificadas nessa volta, 1
não estava nas fontes: uma frase do artigo 128.º citada no plural.

## Estrutura

```
app.py                  interface (Streamlit): chat, fontes, barra lateral
rag/pdfs.py             leitura dos PDFs: markdown, tabelas, limpeza, verificação
rag/estrutura.py        divisão em capítulos/secções/artigos e em trechos
rag/indice.py           cache em dados/, pesquisa BM25, mapa dos documentos
rag/texto.py            português: acentos, plurais, "página 12", "artigo 58.º-A"
rag/assistente.py       ligação à Groq: preparar a pesquisa, escolher fontes, responder
indexar.py              ler os PDFs pelo terminal, com progresso
testes/avaliar.py       bateria de perguntas com respostas verificadas
iniciar.bat             instalar e abrir no Windows com duplo clique
```

## Limitações

- **Imagens**: o texto dentro de imagens não é lido (ex.: a citação da página 5 do Projeto
  Educativo). Do organograma só se aproveitam os nomes das caixas, sem a hierarquia. As fórmulas da
  página 4 (TPS e TCD) também não, mas a explicação em texto delas sim.
- **PDFs digitalizados** (fotografias/scans) não têm texto: o chatbot avisa na barra lateral.
  Precisam de OCR primeiro (por exemplo com o `ocrmypdf`).
- O **plano gratuito** da Groq tem 8 000 tokens por minuto por modelo; cada pergunta gasta ~3 000
  no modelo pequeno e ~4 000 no grande. Com perguntas muito seguidas, a resposta pode demorar uns
  segundos a mais (a biblioteca espera e tenta de novo).
- Há também um limite **diário** de 200 000 tokens por modelo, que recupera aos poucos (~8 000 por
  hora): dá para ~50–60 perguntas seguidas por dia. A bateria completa de testes gasta quase todo
  esse limite. Quando o modelo pequeno chega ao limite, a pesquisa passa a ser preparada pelo
  `qwen`; quando é o grande, a app avisa e pode escolher-se outro modelo na barra lateral.
- Os trechos dos PDFs relevantes para cada pergunta são **enviados para a Groq** (serviço na cloud).
- Como qualquer IA, pode errar. Confirma sempre na fonte indicada (botão *Ver no PDF*).
