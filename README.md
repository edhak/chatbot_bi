# BI Analytics Agent

Sistema de Inteligencia de Negocios (BI) de nivel producción que permite a los usuarios hacer preguntas en **lenguaje natural** sobre un cubo Tabular de Microsoft SSAS, procesarlas a través de un **agente inteligente** (LangGraph + DeepSeek) y visualizar respuestas narrativas junto con **gráficos interactivos** (Apache ECharts).

El proyecto está completamente desacoplado en dos módulos independientes dentro de la misma raíz:

| Módulo | Tecnología | Rol |
|---|---|---|
| `/agent_api` | Python, FastAPI, LangGraph, DeepSeek | Cerebro analítico: genera DAX, ejecuta consultas y empaqueta configuraciones de gráficos |
| `/frontend_ui` | Nuxt 3, Vue 3, TypeScript, Tailwind CSS | Interfaz de chat + BFF (Backend-for-Frontend) que protege las llamadas al agente |

---

## Tabla de Contenidos

- [Arquitectura](#arquitectura)
- [Stack Tecnológico](#stack-tecnológico)
- [Estructura del Proyecto](#estructura-del-proyecto)
- [Modelo de Datos del Cubo](#modelo-de-datos-del-cubo)
- [Requisitos Previos](#requisitos-previos)
- [Configuración tras clonar desde GitHub](#configuración-tras-clonar-desde-github)
- [Variables de Entorno](#variables-de-entorno)
- [Instalación y Ejecución](#instalación-y-ejecución)
  - [Backend – agent_api (Conda py312da)](#1-backend--agent_api-conda-py312da)
  - [Frontend – frontend_ui (Docker blissful_babbage)](#2-frontend--frontend_ui-docker-blissful_babbage)
  - [Frontend – desarrollo local sin Docker](#3-frontend--desarrollo-local-sin-docker)
- [Probar el Flujo Completo](#probar-el-flujo-completo)
- [API Reference](#api-reference)
- [Flujo Interno del Agente](#flujo-interno-del-agente)
- [Subagentes (detalle)](documentacion/subagentes/README.md)
- [Conexión a SSAS en Producción](#conexión-a-ssas-en-producción)
- [Solución de Problemas](#solución-de-problemas)

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                         USUARIO (Browser)                       │
└──────────────────────────────┬──────────────────────────────────┘
                               │ POST /api/chat
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│              frontend_ui  (Nuxt 3 + BFF)                      │
│  ┌──────────────┐  ┌─────────────────┐  ┌───────────────────┐  │
│  │ ChatInterface│  │ server/api/     │  │ plugins/echarts   │  │
│  │   .vue       │  │ chat.post.ts    │  │ (v-chart global)  │  │
│  └──────────────┘  └────────┬────────┘  └───────────────────┘  │
└─────────────────────────────┼───────────────────────────────────┘
                              │ POST /api/v1/query
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              agent_api  (FastAPI + LangGraph)                   │
│  ┌──────────┐  ┌──────────────┐  ┌─────────────────────────┐ │
│  │ main.py  │→ │ core/graph.py│→ │ tools/ssas + filter_lookup │ │
│  │ (FastAPI)│  │ multi-agente │  │ (execute / lookup valores) │ │
│  └──────────┘  └──────┬───────┘  └─────────────┬──────────────┘ │
│                         │                        │               │
│              ┌──────────▼───────────┐            ▼               │
│              │ core/agents/         │     ┌──────────────┐      │
│              │ translator·profiler  │     │ SSAS Tabular │      │
│              │ viz·narrative        │     │  (o mock)    │      │
│              └──────────────────────┘     └──────────────┘      │
│              metadata/cube_dictionary.py (prompt DAX)            │
└─────────────────────────────────────────────────────────────────┘
```

**Principio de seguridad:** la dirección del cubo (`cube_address`) **nunca** se inyecta en el prompt del LLM. Se pasa exclusivamente a través del contexto configurable de LangChain (`config["configurable"]["cube_address"]`), de modo que el agente no la expone ni la alucina.

---

## Stack Tecnológico

### Backend (`/agent_api`)

| Componente | Librería |
|---|---|
| API HTTP | FastAPI + Uvicorn |
| Orquestación del agente | LangGraph (pipeline multi-agente) |
| LLM | DeepSeek vía `ChatOpenAI` (`base_url` apuntando a la API de DeepSeek) |
| Herramientas | LangChain `@tool` (`lookup_dimension_values`, ejecución DAX) |
| Validación de datos | Pydantic v2 |
| Fuente de datos | Cubo Tabular SSAS (consultas DAX) |

### Frontend (`/frontend_ui`)

| Componente | Librería |
|---|---|
| Framework | Nuxt 3 + Vue 3 (Composition API) |
| Lenguaje | TypeScript |
| Estilos | Tailwind CSS |
| Gráficos | Apache ECharts + `vue-echarts` (`<v-chart>`) |
| BFF | Nitro server routes (`server/api/`) |

---

## Estructura del Proyecto

```
200-code-agente-da/
│
├── agent_api/                          # Backend del agente IA
│   ├── metadata/
│   │   └── cube_dictionary.py          # Diccionario estático del cubo (fuente de verdad)
│   ├── core/
│   │   ├── state.py                    # AgentState del pipeline multi-agente
│   │   ├── graph.py                    # StateGraph: translator → execute → profiler → viz
│   │   ├── chart_selector.py           # Catálogo y scoring de gráficos ECharts
│   │   ├── chart_builder.py            # Construye echarts_config desde raw_data
│   │   └── agents/                     # Agentes especializados
│   │       ├── dax_translator.py       # NL → DAX (+ lookup filtros)
│   │       ├── execute_dax.py          # Ejecución SSAS / mock
│   │       ├── data_profiler.py        # Perfil de metadatos
│   │       ├── visualization.py        # Selección de gráfico
│   │       └── narrative.py            # Narrativa ejecutiva / error
│   ├── tools/
│   │   ├── ssas_executor.py            # @tool execute_dax_query
│   │   └── filter_lookup.py            # lookup_dimension_values (Perú→PERU)
│   ├── main.py                         # Servidor FastAPI
│   ├── data/
│   │   ├── dashboard.json.example      # Plantilla del dashboard ejecutivo
│   │   └── dashboard.json              # (no commitear – datos locales)
│   ├── requirements.txt
│   ├── .env.example
│   └── .env                            # (no commitear – ver .gitignore)
│
├── frontend_ui/                        # Frontend + BFF
│   ├── server/
│   │   └── api/
│   │       └── chat.post.ts            # BFF: proxy seguro al backend Python
│   ├── plugins/
│   │   └── echarts.ts                  # Registro global de <v-chart>
│   ├── components/
│   │   └── ChatInterface.vue           # UI de chat, gráficos y acordeón DAX
│   ├── assets/css/
│   │   └── main.css                    # Estilos base + Tailwind
│   ├── app.vue                         # Página de entrada
│   ├── nuxt.config.ts
│   ├── package.json
│   ├── tsconfig.json
│   ├── .env.example
│   └── .env                            # (no commitear)
│
├── .gitignore
├── pyproject.toml                      # Instalación editable del paquete agent_api
├── scripts/
│   ├── .env.cube.example               # Plantilla de conexión SSAS para pruebas
│   ├── .env.cube                       # (no commitear – cadena ADOMD real)
│   ├── visualizar_langgraph.py         # Exporta diagrama del grafo compilado
│   ├── run_backend.ps1                 # Script de arranque (PowerShell)
│   └── run_backend.bat                 # Script de arranque (CMD)
├── documentacion/                      # Portal HTML, Word y diagramas LangGraph
└── README.md
```

---

## Modelo de Datos del Cubo

El archivo `agent_api/metadata/cube_dictionary.py` es la **única fuente de verdad** del esquema. El LLM recibe este diccionario en su System Prompt para evitar alucinaciones.

### Medidas

| Medida DAX | Descripción |
|---|---|
| `[Ventas Totales]` | Suma del monto total de ventas |
| `[Cantidad Solicitada]` | Unidades solicitadas por clientes |
| `[Margen Ganancia]` | Diferencia entre ingresos y costo de ventas |

### Dimensiones y Jerarquías

| Dimensión | Jerarquía |
|---|---|
| `Dim_Fecha` | Año → Trimestre → Mes |
| `Dim_Producto` | Categoría → Subcategoría → Producto |
| `Dim_Geografia` | País → Región → Ciudad |

---

## Requisitos Previos

| Herramienta | Versión | Uso |
|---|---|---|
| **Anaconda** con entorno `py312da` | Python 3.12 | Backend Python |
| **Node.js** | ≥ 18 | Frontend Nuxt |
| **Docker** | Cualquier versión reciente | Contenedor `blissful_babbage` para el frontend |
| **API Key de DeepSeek** | — | [platform.deepseek.com](https://platform.deepseek.com) |

---

## Configuración tras clonar desde GitHub

El repositorio **no incluye** archivos con secretos, credenciales ni datos generados en tu máquina. Tras `git clone`, créalos a partir de las plantillas `.example` incluidas en el código.

### Archivos que debes crear localmente

| Archivo local | ¿Por qué no está en GitHub? | Plantilla en el repo |
|---|---|---|
| `agent_api/.env` | API key de DeepSeek, cadena del cubo SSAS | `agent_api/.env.example` |
| `frontend_ui/.env` | URL del backend según tu entorno (Docker o local) | `frontend_ui/.env.example` |
| `scripts/.env.cube` | Cadena ADOMD para probar conexión al cubo | `scripts/.env.cube.example` |
| `agent_api/data/dashboard.json` | Indicadores guardados por usuarios en el dashboard | `agent_api/data/dashboard.json.example` |

También se ignoran carpetas generadas automáticamente: `.venv/`, `node_modules/`, `.nuxt/`, `__pycache__/`, logs, etc. (ver `.gitignore`).

### Configuración rápida (PowerShell, desde la raíz del proyecto)

```powershell
# 1. Backend — variables de entorno
copy agent_api\.env.example agent_api\.env
notepad agent_api\.env   # Editar: DEEPSEEK_API_KEY y DEFAULT_CUBE_ADDRESS

# 2. Frontend — URL del agente Python
copy frontend_ui\.env.example frontend_ui\.env
# Si usa Docker: dejar AGENT_API_URL=http://host.docker.internal:8000
# Si corre Nuxt en local: cambiar a http://localhost:8000

# 3. Scripts — prueba de cubo SSAS (opcional)
copy scripts\.env.cube.example scripts\.env.cube
notepad scripts\.env.cube   # Editar Data Source e Initial Catalog

# 4. Dashboard ejecutivo — almacén vacío inicial
copy agent_api\data\dashboard.json.example agent_api\data\dashboard.json
```

### Detalle por archivo

#### `agent_api/.env` (obligatorio)

Contiene la configuración del servidor FastAPI y del agente LangGraph.

| Variable | Obligatoria | Descripción |
|---|---|---|
| `DEEPSEEK_API_KEY` | Sí | Clave en [platform.deepseek.com](https://platform.deepseek.com) |
| `DEFAULT_CUBE_ADDRESS` | Sí* | Cadena ADOMD: `Provider=MSOLAP;Data Source=HOST;Initial Catalog=CUBO;` |
| `SSAS_USE_MOCK` | No | `true` = datos simulados sin SSAS (útil sin VPN/red corporativa) |
| `CORS_ORIGINS` | No | Orígenes permitidos del frontend (por defecto `http://localhost:3000`) |
| `AGENT_DEBUG` | No | `true` = logs detallados del agente |

\* No es obligatoria si `SSAS_USE_MOCK=true`.

#### `frontend_ui/.env` (obligatorio para Docker o dev local)

| Variable | Valor típico | Cuándo usarla |
|---|---|---|
| `AGENT_API_URL` | `http://host.docker.internal:8000` | Frontend en contenedor Docker (Windows) |
| `AGENT_API_URL` | `http://localhost:8000` | `npm run dev` sin Docker |

> **Nota:** `scripts/docker-up.ps1` puede generar `frontend_ui/.env` automáticamente con la IP detectada del host. Si lo usas, no hace falta copiar la plantilla manualmente.

#### `scripts/.env.cube` (opcional)

Solo para el script de diagnóstico `scripts/test_cube_connection.py`. No lo usa el backend en runtime; el backend lee `DEFAULT_CUBE_ADDRESS` desde `agent_api/.env`.

```powershell
python scripts/test_cube_connection.py
```

#### `agent_api/data/dashboard.json` (opcional)

Persistencia local de los indicadores del **Dashboard ejecutivo**. Si no existe, el backend arranca igual y usa un almacén vacío en memoria hasta el primer guardado. Para dejarlo explícito desde el inicio:

```powershell
copy agent_api\data\dashboard.json.example agent_api\data\dashboard.json
```

Contenido inicial:

```json
{"version": 1, "items": []}
```

### Verificar que no subirás secretos

Antes del primer `git push`, comprueba que los archivos sensibles están ignorados:

```powershell
git status
# No deben aparecer: agent_api/.env, frontend_ui/.env, scripts/.env.cube, agent_api/data/dashboard.json

git check-ignore -v agent_api\.env frontend_ui\.env scripts\.env.cube agent_api\data\dashboard.json
# Debe mostrar la regla del .gitignore que los excluye
```

---

## Variables de Entorno

### Backend – `agent_api/.env`

Ver plantilla completa en `agent_api/.env.example`. Variables principales:

```env
DEEPSEEK_API_KEY=sk-your-deepseek-api-key   # Obligatorio
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
LLM_TIMEOUT_SEC=60
HOST=0.0.0.0
PORT=8000
CORS_ORIGINS=http://localhost:3000
DEFAULT_CUBE_ADDRESS=Provider=MSOLAP;Data Source=YOUR_SSAS_HOST;Initial Catalog=CB_BI_FlotHs;
SSAS_USE_MOCK=false
ALLOW_CLIENT_CUBE_ADDRESS=false
AGENT_DEBUG=true
AGENT_REQUEST_TIMEOUT_SEC=90
AGENT_RECURSION_LIMIT=10
```

```powershell
copy agent_api\.env.example agent_api\.env
```

### Frontend – `frontend_ui/.env`

```env
# Desde Docker (contenedor → host Windows):
AGENT_API_URL=http://host.docker.internal:8000

# Desde desarrollo local sin Docker:
# AGENT_API_URL=http://localhost:8000
```

```powershell
copy frontend_ui\.env.example frontend_ui\.env
```

### Scripts – `scripts/.env.cube` (opcional, pruebas SSAS)

```env
CUBE_ADDRESS=Provider=MSOLAP;Data Source=YOUR_SSAS_HOST;Initial Catalog=CB_BI_FlotHs;
```

```powershell
copy scripts\.env.cube.example scripts\.env.cube
```

---

## Instalación y Ejecución

### 1. Backend – `agent_api` (Conda `py312da`)

```powershell
# 1. Activar el entorno Conda
conda activate py312da

# 2. Ir a la raíz del proyecto (carpeta que contiene agent_api/ y frontend_ui/)
cd ruta\al\200-code-agente-da

# 3. Instalar el paquete en modo editable (resuelve el error ModuleNotFoundError)
pip install -e .

# 4. Configurar variables de entorno (si aún no lo hiciste)
copy agent_api\.env.example agent_api\.env
# Editar agent_api\.env y colocar tu DEEPSEEK_API_KEY real

# 5. Levantar el servidor FastAPI
uvicorn agent_api.main:app --host 0.0.0.0 --port 8000 --reload
```

**Opción rápida con script** (hace el `pip install -e .` automáticamente):

```powershell
conda activate py312da
.\scripts\run_backend.ps1
```

**Verificar que el backend está activo:**

```
GET http://localhost:8000/health
→ {"status": "ok"}
```

Documentación interactiva de la API (Swagger):

```
http://localhost:8000/docs
```

---

### 2. Frontend – `frontend_ui` (Docker `blissful_babbage`)

El servidor Node/Nuxt corre dentro del contenedor Docker llamado **`blissful_babbage`**.

```powershell
# 1. Verificar estado del contenedor
docker ps -a --filter "name=blissful_babbage"

# 2. Arrancar el contenedor si está detenido
docker start blissful_babbage

# 3. Entrar al contenedor
docker exec -it blissful_babbage bash

# --- Dentro del contenedor ---

# 4. Ir al directorio del frontend (ajusta la ruta según tu montaje de volumen)
cd /app/frontend_ui   # o la ruta donde esté montado el proyecto

# 5. Instalar dependencias (solo la primera vez)
npm install

# 6. Configurar .env apuntando al host donde corre Python
echo "AGENT_API_URL=http://host.docker.internal:8000" > .env

# 7. Levantar Nuxt en modo desarrollo
npm run dev -- --host 0.0.0.0
```

Abre en el navegador: **`http://localhost:3000`**

> `host.docker.internal` es el hostname especial de Docker Desktop en Windows que permite al contenedor alcanzar servicios corriendo en la máquina host (donde está el FastAPI con Conda).

---

### 3. Frontend – desarrollo local sin Docker

Si prefieres correr Nuxt directamente en tu máquina sin el contenedor:

```powershell
cd frontend_ui

npm install

# Usar localhost ya que backend y frontend están en la misma máquina
echo "AGENT_API_URL=http://localhost:8000" > .env

npm run dev
```

Abre: **`http://localhost:3000`**

---

## Probar el Flujo Completo

Con ambos servidores activos:

1. Abre `http://localhost:3000`
2. Verifica que el campo **Dirección del cubo** tenga una cadena de conexión ADOMD (viene con un valor por defecto de ejemplo)
3. Escribe una pregunta en lenguaje natural, por ejemplo:

   ```
   ¿Cuáles son las ventas totales por categoría de producto?
   ```

4. El agente:
   - Traduce la pregunta a una consulta DAX
   - Ejecuta la consulta (datos mock en desarrollo)
   - Devuelve una explicación narrativa
   - Renderiza un gráfico interactivo ECharts
5. Haz clic en **"Ver consulta DAX"** en la respuesta del agente para auditar la consulta generada

### Más ejemplos de preguntas

```
Muéstrame la evolución de ventas por mes en 2024
¿Qué regiones tienen mayor margen de ganancia?
Compara la cantidad solicitada por subcategoría de producto
```

---

## API Reference

### `POST /api/v1/query` (Backend Python)

**Request:**

```json
{
  "cube_address": "Provider=MSOLAP;Data Source=localhost;Initial Catalog=VentasCube;",
  "question": "¿Cuáles son las ventas totales por categoría?"
}
```

**Response:**

```json
{
  "text_response": "Las ventas totales por categoría muestran que...",
  "dax_query": "EVALUATE SUMMARIZECOLUMNS(Dim_Producto[Categoría], \"Ventas Totales\", [Ventas Totales])",
  "echarts_config": {
    "title": { "text": "Ventas por Categoría" },
    "tooltip": { "trigger": "axis" },
    "xAxis": { "type": "category", "data": ["Electrónica", "Ropa"] },
    "yAxis": { "type": "value" },
    "series": [{ "name": "Ventas", "type": "bar", "data": [125000, 98000] }]
  },
  "raw_data": [
    { "Categoría": "Electrónica", "Ventas Totales": 125000.75 }
  ]
}
```

### `POST /api/chat` (BFF Nuxt – uso interno del frontend)

**Request:**

```json
{
  "message": "¿Cuáles son las ventas totales por categoría?",
  "cube_address": "Provider=MSOLAP;Data Source=localhost;Initial Catalog=VentasCube;"
}
```

**Response:**

```json
{
  "text": "Las ventas totales por categoría muestran que...",
  "dax": "EVALUATE SUMMARIZECOLUMNS(...)",
  "chartConfig": { "...echarts_config..." }
}
```

### `GET /health` (Backend Python)

```json
{ "status": "ok" }
```

---

## Flujo Interno del Agente

El grafo LangGraph implementa un **pipeline multi-agente** (línea de ensamblaje). Cada nodo tiene una sola responsabilidad:

```
__start__
    │
    ▼
dax_translator_agent     # Solo genera DAX (diccionario cubo + lookup filtros)
    │
    ▼
execute_dax_node         # Ejecuta DAX en SSAS / mock
    │
    ├── error && dax_retries < MAX_DAX_RETRIES (3) ──► dax_translator_agent
    ├── error && dax_retries >= MAX               ──► error_response → __end__
    └── ok
         ▼
data_profiler_agent      # Resume forma de los datos (metadatos)
         ▼
visualization_agent      # Elige gráfico ECharts (catálogo + reglas)
         ▼
narrative_agent          # Narrativa ejecutiva para el usuario
         ▼
      __end__  →  JSON { text_response, dax_query, echarts_config }
```

| Nodo | Entrada clave | Salida clave |
|---|---|---|
| `dax_translator_agent` | `user_query` (+ error previo) | `generated_dax` |
| `execute_dax_node` | `generated_dax` | `dax_execution_result`, `dax_retries` |
| `data_profiler_agent` | filas OK | `data_profile_summary` |
| `visualization_agent` | pregunta + perfil | `chart_configuration` |
| `narrative_agent` | datos + perfil | `response_text` |

**Documentación detallada por subagente** (estructura interna, I/O, dependencias):

→ [`documentacion/subagentes/`](documentacion/subagentes/README.md)

**Qué se reutiliza del diseño anterior:**
- Diccionario del cubo (`cube_dictionary.py`) solo en el traductor DAX
- `lookup_dimension_values` para filtros (Perú → PERU)
- `chart_selector` / `chart_builder` (bar, line, pie, treemap, etc.)
- Contrato API sin cambios: `run_agent()` → `text_response`, `dax_query`, `echarts_config`

**Diagrama desde código real:**

```powershell
python scripts/visualizar_langgraph.py --no-open
# Salida: documentacion/imagenes/langgraph-generado/
```

---

## Conexión a SSAS en Producción

Por defecto, `tools/ssas_executor.py` devuelve un **DataFrame mock** de Pandas para desarrollo sin necesidad de un servidor SSAS real.

Para conectar a un cubo Tabular real, edita `agent_api/tools/ssas_executor.py` y descomenta una de las dos opciones documentadas en el archivo:

### Opción A – `pyadomd` (conexión ADOMD nativa)

```python
pip install pyadomd

from pyadomd import Pyadomd
with Pyadomd(cube_address) as conn:
    with conn.cursor().execute(dax_query) as cursor:
        columns = [col[0].name for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
return rows
```

### Opción B – Endpoint XMLA (HTTP)

```python
import requests
response = requests.post(
    f"{cube_address}/xmla",
    json={"query": dax_query},
    auth=("domain\\user", "password"),
    timeout=60,
)
```

---

## Solución de Problemas

| Problema | Causa probable | Solución |
|---|---|---|
| `ModuleNotFoundError: agent_api` | Paquete no instalado en el entorno | Desde la raíz del proyecto: `pip install -e .` o ejecutar `.\scripts\run_backend.ps1` |
| `DEEPSEEK_API_KEY no está configurada` | Falta el `.env` del backend | Copiar y completar `agent_api/.env` |
| Frontend no conecta al backend desde Docker | URL incorrecta en `.env` | Usar `http://host.docker.internal:8000` dentro del contenedor |
| Error CORS en el navegador | Origen no permitido | Agregar la URL del frontend en `CORS_ORIGINS` del backend |
| `blissful_babbage` no arranca | Contenedor detenido | `docker start blissful_babbage` |
| Gráfico no se renderiza | SSR de ECharts | El componente `<v-chart>` está envuelto en `<ClientOnly>` – verificar que el plugin `echarts.ts` esté activo |
| Timeout en consultas largas | LLM tarda en responder | El BFF tiene timeout de 120s; ajustar en `chat.post.ts` si es necesario |
| `conda` no reconocido en PowerShell | Conda no inicializado en el shell | Ejecutar `conda init powershell` y reiniciar la terminal, o usar Anaconda Prompt |

---

## Scripts Útiles

```powershell
# Backend – arranque con script (recomendado)
.\scripts\run_backend.ps1

# Backend – modo producción (sin reload)
uvicorn agent_api.main:app --host 0.0.0.0 --port 8000

# Frontend – build de producción
cd frontend_ui
npm run build
npm run preview

# Ver logs del contenedor Docker
docker logs -f blissful_babbage

# Reiniciar contenedor Docker
docker restart blissful_babbage
```

---

## Licencia

Proyecto interno – RESEMIN S.A.
