# Arranca el backend FastAPI del agente BI.
# Uso: .\scripts\run_backend.ps1

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "Proyecto: $ProjectRoot" -ForegroundColor Cyan

# Instalar el paquete en modo editable (solo la primera vez o tras cambios en pyproject.toml)
pip install -e . --quiet

Write-Host "Iniciando uvicorn en http://0.0.0.0:8000 ..." -ForegroundColor Green
uvicorn agent_api.main:app --host 0.0.0.0 --port 8000 --reload
