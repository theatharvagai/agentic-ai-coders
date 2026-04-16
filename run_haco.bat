@echo off
title HACO - Hardware-Aware Code Optimizer
echo Starting HACO Dashboard...
cd /d "%~dp0"
if not exist .venv (
    echo Error: Virtual environment .venv not found.
    pause
    exit /b
)
if not exist ".venv\Scripts\python.exe" (
    echo Error: Python executable not found in .venv\Scripts\
    pause
    exit /b
)
echo Launching Streamlit via virtualenv Python...
".venv\Scripts\python.exe" -m streamlit run app.py
pause
