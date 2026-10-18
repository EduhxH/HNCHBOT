@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo A criar o ambiente virtual...
    py -3 -m venv .venv 2>nul || python -m venv .venv
    if not exist ".venv\Scripts\python.exe" (
        echo Nao encontrei o Python. Instala-o em https://www.python.org/downloads/
        pause
        exit /b 1
    )
    echo A instalar as dependencias ^(so na primeira vez^)...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo.
    echo Criei o ficheiro .env - abre-o e coloca la a tua chave da Groq.
    echo.
)

".venv\Scripts\python.exe" -m streamlit run app.py
pause
