@echo off
cd /d "%~dp0\.."
echo Proyecto: %CD%

if not exist "agent_api\.env" (
    echo AVISO: No existe agent_api\.env
    echo   Copie agent_api\.env.example a agent_api\.env y complete DEEPSEEK_API_KEY y DEFAULT_CUBE_ADDRESS.
)

pip install -e . --quiet

if /I "%UVICORN_RELOAD%"=="false" (
    echo Iniciando uvicorn en http://0.0.0.0:8000 sin reload...
    uvicorn agent_api.main:app --host 0.0.0.0 --port 8000
) else (
    echo Iniciando uvicorn en http://0.0.0.0:8000 con reload...
    uvicorn agent_api.main:app --host 0.0.0.0 --port 8000 --reload
)
