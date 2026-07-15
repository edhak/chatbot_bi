@echo off
cd /d "%~dp0\.."
echo Proyecto: %CD%
pip install -e . --quiet
echo Iniciando uvicorn en http://0.0.0.0:8000 ...
uvicorn agent_api.main:app --host 0.0.0.0 --port 8000 --reload
