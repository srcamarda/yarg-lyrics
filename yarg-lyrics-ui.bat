@echo off
rem Abre a interface do yarg-lyrics no navegador (http://127.0.0.1:8765). Feche esta janela para encerrar.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if exist ".venv-rocm\Scripts\python.exe" (
  ".venv-rocm\Scripts\python.exe" ui\server.py
) else (
  ".venv\Scripts\python.exe" ui\server.py
)
pause
