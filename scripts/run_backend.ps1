# Arranca el backend FastAPI del agente BI.
# Uso: .\scripts\run_backend.ps1

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "Proyecto: $ProjectRoot" -ForegroundColor Cyan

$EnvFile = Join-Path $ProjectRoot "agent_api\.env"
if (-not (Test-Path $EnvFile)) {
    Write-Host "AVISO: No existe agent_api\.env" -ForegroundColor Yellow
    Write-Host "  Copie agent_api\.env.example a agent_api\.env y complete DEEPSEEK_API_KEY y DEFAULT_CUBE_ADDRESS." -ForegroundColor Yellow
}

# Instalar el paquete en modo editable (solo la primera vez o tras cambios en pyproject.toml)
pip install -e . --quiet

$Reload = if ($env:UVICORN_RELOAD) { $env:UVICORN_RELOAD } else { "true" }
$ReloadFlag = if ($Reload -eq "true") { "--reload" } else { "" }

Write-Host "Iniciando uvicorn en http://0.0.0.0:8000 (reload=$Reload) ..." -ForegroundColor Green
if ($ReloadFlag) {
    uvicorn agent_api.main:app --host 0.0.0.0 --port 8000 --reload
} else {
    uvicorn agent_api.main:app --host 0.0.0.0 --port 8000
}
