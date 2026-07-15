# Levanta el frontend en Docker detectando la IP del host Windows
# para que el contenedor pueda alcanzar el backend FastAPI en el puerto 8000.

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "=== Docker Frontend + deteccion de IP del host ===" -ForegroundColor Cyan

# Obtener IP local (excluir Docker/WSL/loopback)
$hostIp = (
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
        $_.IPAddress -notlike '127.*' -and
        $_.IPAddress -notlike '169.254.*' -and
        $_.InterfaceAlias -notlike '*Docker*' -and
        $_.InterfaceAlias -notlike '*vEthernet*'
    } |
    Select-Object -First 1 -ExpandProperty IPAddress
)

if (-not $hostIp) {
    Write-Host "No se detecto IP del host. Usando host.docker.internal" -ForegroundColor Yellow
    $hostIp = ""
}

Write-Host "IP del host detectada: $($hostIp ?? '(ninguna)')" -ForegroundColor Green

# Verificar que el backend responde en el host
Write-Host "Verificando backend en http://localhost:8000/health ..."
try {
    $health = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 5
    Write-Host "Backend OK: $($health | ConvertTo-Json -Compress)" -ForegroundColor Green
} catch {
    Write-Host "ADVERTENCIA: Backend no responde en localhost:8000" -ForegroundColor Red
    Write-Host "Inicie primero:" -ForegroundColor Yellow
    Write-Host "  uvicorn agent_api.main:app --host 0.0.0.0 --port 8000 --reload" -ForegroundColor Yellow
    Write-Host ""
}

# Regla de firewall (opcional, requiere admin)
$fwRule = Get-NetFirewallRule -DisplayName "Agent API Docker 8000" -ErrorAction SilentlyContinue
if (-not $fwRule) {
    Write-Host "Tip: Si Docker no conecta, ejecute como Admin:" -ForegroundColor Yellow
    Write-Host '  New-NetFirewallRule -DisplayName "Agent API Docker 8000" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow' -ForegroundColor Gray
}

Set-Location $ProjectRoot

$env:HOST_IP = $hostIp
docker rm -f blissful_babbage 2>$null
docker compose up
