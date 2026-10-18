# ⚛️ Assistente de Físico-Química — chatbot para vários PDFs

Demo de um chatbot que **só responde com base nos PDFs** que estão na pasta `documentos/`.
Serve para encontrar rapidamente uma parte específica de um documento, por exemplo:

- *"O que diz a Lei de Lavoisier?"*
- *"O que significa o 2.º parágrafo da página 3 do documento Movimentos e Forças?"*
- *"Em que documento se fala de indicadores ácido-base?"*
- *"E na página seguinte?"* (percebe perguntas de seguimento)

Cada resposta indica **o documento e a página** de onde veio a informação, por exemplo `[1]`.
Ao clicar em **🔍 Ver página no PDF**, abre-se a página original com o trecho destacado a amarelo.

Usa a API da [Groq](https://console.groq.com) (modelo `openai/gpt-oss-120b` por defeito) e
uma interface em [Streamlit](https://streamlit.io). A lista de modelos é pedida à Groq quando o
chatbot abre, por isso continua a funcionar quando a Groq retira modelos (já aconteceu com os Llama).

---

## Como funciona

```
PDFs ──► extrair texto por página e parágrafo (PyMuPDF) ──► índice de pesquisa (BM25)
                                                                    │
pergunta ──► Groq (modelo pequeno) reescreve a pergunta, ───────────┤
             sugere palavras-chave, documento e página              ▼
                                                     trechos mais relevantes
                                                     + página completa se for pedida
                                                                    │
                                                                    ▼
                       Groq (modelo grande) responde SÓ com esses trechos e cita [n]
```

1. **Leitura dos PDFs**: o texto de cada página é extraído e dividido em parágrafos.
   Fica guardado em `dados/indice.json`, por isso cada PDF só é lido uma vez.
   Se um PDF for alterado ou adicionado, é lido de novo automaticamente.
2. **Pesquisa**: usa **BM25**, o algoritmo clássico dos motores de busca por palavras-chave,
   adaptado ao português (ignora acentos, plurais e palavras como "de", "o", "que").
   A Groq não tem modelos de *embeddings*, por isso não se usa uma base de dados vetorial
   (como o ChromaDB do projeto [AGENTE-IA](https://github.com/EduhxH/AGENTE-IA)). Assim, também
   não é preciso descarregar modelos, e corre em qualquer PC.
3. **Reescrita da pergunta**: antes de pesquisar, um modelo pequeno e rápido (`openai/gpt-oss-20b`)
   transforma perguntas como *"e isso?"* numa pergunta completa e acrescenta sinónimos.
4. **Páginas**: se a pergunta referir uma página (*"página 12"*, *"pág. 3 a 5"*, *"p. 7"*),
   a página inteira é enviada com os parágrafos numerados (§1, §2, ...).
5. **Resposta**: o modelo recebe só os trechos encontrados e é instruído a não inventar.
   Se a informação não estiver nos PDFs, diz que não encontrou.

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
streamlit run app.py
```

### Chave da Groq

1. Criar conta em https://console.groq.com e gerar uma chave em **API Keys**. O plano gratuito chega para a demo.
2. Colocá-la no ficheiro `.env`:
   ```
   GROQ_API_KEY=gsk_...
   ```
   Também se pode colar na barra lateral do chatbot, no campo *Chave da API Groq*.

Sem chave, o chatbot continua a funcionar em modo de pesquisa: mostra os trechos e páginas encontrados, mas não escreve respostas.

## Adicionar documentos

- Copiar os PDFs para a pasta **`documentos/`** (pode ter subpastas), **ou**
- Arrastá-los para o campo **Adicionar PDFs** na barra lateral.

Com muitos PDFs, pode-se correr `python indexar.py` antes de abrir o chatbot para ver o progresso.

Os 3 PDFs que vêm na pasta (`Movimentos e Forcas.pdf`, `Reacoes Quimicas.pdf`,
`Atomos e Tabela Periodica.pdf`) são **textos de exemplo** criados para testar
(`python exemplos/gerar_pdfs_exemplo.py`). Podem ser apagados.

## Estrutura

```
app.py                  interface (Streamlit): chat, fontes, barra lateral
rag/pdfs.py             extrair texto dos PDFs, dividir em trechos, desenhar página com destaque
rag/indice.py           ler a pasta documentos/, guardar cache, pesquisa BM25, detetar "página N"
rag/assistente.py       ligação à Groq: reescrever pergunta, escolher fontes, responder com citações
indexar.py              ler todos os PDFs pelo terminal (opcional)
iniciar.bat             instalar e abrir no Windows com duplo clique
documentos/             os PDFs
dados/indice.json       cache do texto extraído (criada automaticamente)
exemplos/               gerador dos PDFs de exemplo
```

## Limitações

- **PDFs digitalizados** (fotografias/scans) não têm texto: o chatbot avisa na barra lateral.
  Para esses é preciso OCR primeiro (por exemplo com o `ocrmypdf`).
- A pesquisa é por **palavras**: se a pergunta usar palavras muito diferentes das do documento,
  pode não encontrar. Ajuda indicar o documento ou a página. A reescrita com sinónimos reduz este problema.
- O **plano gratuito** da Groq tem limites de pedidos por minuto. Se aparecer o aviso, espera-se um minuto.
- Os trechos dos PDFs relevantes para cada pergunta são **enviados para a Groq** (serviço na cloud).
  Não usar com documentos confidenciais.
- Como qualquer IA, pode errar. Confirme sempre na fonte indicada (botão *Ver página no PDF*).
