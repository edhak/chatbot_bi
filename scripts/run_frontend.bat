@echo off
REM Arranca el frontend SIN Docker — conecta directo a localhost:8000
cd /d "%~dp0\..\frontend_ui"

echo ============================================
echo  Frontend LOCAL (sin Docker)
echo  Backend esperado en: http://localhost:8000
echo ============================================

if not exist node_modules (
    echo Instalando dependencias...
    call npm install
)

echo AGENT_API_URL=http://localhost:8000> .env
echo ALLOW_CLIENT_CUBE_ADDRESS=false>> .env

echo.
echo Iniciando Nuxt en http://localhost:3000 ...
call npm run dev
