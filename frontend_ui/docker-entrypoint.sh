#!/bin/sh
set -e

echo "==> Instalando dependencias (sin postinstall)..."
npm install --ignore-scripts

echo "==> Limpiando build anterior de Nuxt..."
find /app/.nuxt -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null || true
find /app/.output -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null || true

echo "==> Generando artefactos Nuxt (nuxt prepare)..."
npx nuxt prepare

if [ ! -f /app/.nuxt/nuxt.json ]; then
  echo "ERROR: nuxt prepare no genero .nuxt/nuxt.json"
  exit 1
fi

echo "==> Iniciando servidor de desarrollo..."
exec npx nuxt dev --host 0.0.0.0 --port 3000
