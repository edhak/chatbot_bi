#!/usr/bin/env python3
"""
Visualiza el grafo LangGraph compilado del agente BI.

No modifica el código del agente: solo importa agent_graph y exporta diagramas.

Uso:
    python scripts/visualizar_langgraph.py
    python scripts/visualizar_langgraph.py --output documentacion/imagenes/langgraph-generado

Salidas:
    - langgraph-oficial.mmd      Mermaid generado por LangGraph
    - langgraph-oficial.png      PNG oficial (draw_mermaid_png)
    - langgraph-anotado.mmd      Mermaid con funciones y fase post-grafo
    - langgraph-anotado.html     Visor interactivo en el navegador
    - langgraph-metadata.json    Nodos, aristas y metadatos
    - langgraph-ascii.txt        Diagrama ASCII en texto
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "documentacion" / "imagenes" / "langgraph-generado"

# Metadatos del código fuente (graph.py) — documentación, no altera el grafo.
NODE_META = {
    "agent": {
        "function": "call_model()",
        "description": "LLM con herramientas: genera DAX y llama execute_dax_query",
        "llm": "_llm_tools() · DeepSeek",
    },
    "tools": {
        "function": "_run_tools()",
        "description": "ToolNode → execute_dax_query contra SSAS (o mock)",
        "llm": None,
    },
    "process_results": {
        "function": "_process_tool_results()",
        "description": "Extrae raw_data y current_dax_query de los mensajes",
        "llm": None,
    },
    "validate_results": {
        "function": "validate_results()",
        "description": "Detecta 0 filas o error en ToolMessage; setea validation_error",
        "llm": None,
    },
    "retry_agent": {
        "function": "retry_agent()",
        "description": "Inyecta hint HumanMessage y vuelve a agent (máx. MAX_DAX_RETRIES)",
        "llm": None,
    },
    "finalize": {
        "function": "finalize_response()",
        "description": "Segundo LLM: narrativa con structured output (FinalizeOutput)",
        "llm": "_llm_final() · DeepSeek",
    },
    "no_tool_response": {
        "function": "no_tool_response()",
        "description": "Agente sin tool_calls: respuesta directa al usuario",
        "llm": None,
    },
    "error_response": {
        "function": "error_response()",
        "description": "Tras agotar reintentos DAX: mensaje de error al usuario",
        "llm": None,
    },
}

POST_GRAPH = [
    {
        "step": "resolve",
        "function": "_resolve_response_from_state()",
        "description": "Usa response_text/response_dax del estado si el grafo ya finalizó",
    },
    {
        "step": "parse",
        "function": "_extract_json_from_text()",
        "description": "Fallback: parsea text_response y dax_query del último AIMessage",
    },
    {
        "step": "build",
        "function": "_build_agent_response()",
        "description": "Ensambla payload de respuesta API",
    },
    {
        "step": "chart",
        "function": "ensure_echarts_config()",
        "description": "Genera gráfico ECharts desde raw_data (chart_builder.py)",
    },
]

ANNOTATED_MERMAID = """---
title: Agente BI — LangGraph + Post-proceso
config:
  flowchart:
    curve: basis
    htmlLabels: true
  theme: base
  themeVariables:
    primaryColor: '#0496cd'
    primaryTextColor: '#ffffff'
    lineColor: '#3c3c3b'
    secondaryColor: '#f5c418'
    tertiaryColor: '#e0f4fc'
---
flowchart TD
    classDef startEnd fill:#3c3c3b,stroke:#0496cd,color:#fff
    classDef agent fill:#0496cd,stroke:#0378A4,color:#fff
    classDef tool fill:#f5c418,stroke:#d4a017,color:#1a1a19
    classDef process fill:#10b981,stroke:#059669,color:#fff
    classDef finalize fill:#8b5cf6,stroke:#6d28d9,color:#fff
    classDef warn fill:#f97316,stroke:#c2410c,color:#fff
    classDef post fill:#e0f4fc,stroke:#0496cd,color:#3c3c3b
    classDef decision fill:#1e293b,stroke:#f5c418,color:#f5c418

    START([__start__ / run_agent]):::startEnd
    AGENT["agent<br/>call_model<br/>LLM + bind_tools"]:::agent
    DECISION{"tool_calls?<br/>_route_after_model"}:::decision
    NOTOOL["no_tool_response<br/>sin DAX"]:::warn
    TOOLS["tools<br/>_run_tools<br/>execute_dax_query"]:::tool
    PROC["process_results<br/>_process_tool_results"]:::process
    VALID{"datos OK?<br/>_route_after_validate"}:::decision
    RETRY["retry_agent<br/>hint + reintento"]:::warn
    ERR["error_response<br/>sin datos tras retry"]:::warn
    FIN["finalize<br/>finalize_response<br/>structured output"]:::finalize
    ENDG([__end__ / grafo]):::startEnd

    RESOLVE["resolve<br/>_resolve_response_from_state"]:::post
    PARSE["parse<br/>_extract_json_from_text"]:::post
    BUILD["build<br/>_build_agent_response"]:::post
    CHART["chart<br/>ensure_echarts_config"]:::post
    API["QueryResponse API"]:::startEnd

    START --> AGENT
    AGENT --> DECISION
    DECISION -->|si| TOOLS
    DECISION -->|no| NOTOOL
    NOTOOL --> ENDG
    TOOLS --> PROC --> VALID
    VALID -->|OK| FIN
    VALID -->|retry| RETRY
    VALID -->|error| ERR
    RETRY --> AGENT
    FIN --> ENDG
    ERR --> ENDG
    ENDG --> RESOLVE --> PARSE --> BUILD --> CHART --> API

    subgraph STATE ["AgentState state.py"]
        direction LR
        S1[messages]
        S2[current_dax_query]
        S3[raw_data]
        S4[retry_count]
        S5[validation_error]
        S6["response_text y response_dax"]
        S7[_trace]
    end
"""


def ensure_output_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_compiled_graph():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from agent_api.core.graph import agent_graph

    return agent_graph


def export_official(graph, out_dir: Path) -> dict:
    drawable = graph.get_graph()

    mermaid = drawable.draw_mermaid()
    mmd_path = out_dir / "langgraph-oficial.mmd"
    mmd_path.write_text(mermaid, encoding="utf-8")

    png_path = out_dir / "langgraph-oficial.png"
    png_bytes = drawable.draw_mermaid_png()
    png_path.write_bytes(png_bytes)

    ascii_path = out_dir / "langgraph-ascii.txt"
    try:
        ascii_text = drawable.draw_ascii()
    except ImportError:
        ascii_text = (
            "ASCII no disponible (pip install grandalf).\n\n"
            "Mermaid oficial:\n" + mermaid
        )
    ascii_path.write_text(ascii_text, encoding="utf-8")

    return {
        "mermaid": str(mmd_path.relative_to(ROOT)),
        "png": str(png_path.relative_to(ROOT)),
        "ascii": str(ascii_path.relative_to(ROOT)),
        "png_bytes": len(png_bytes),
    }


def export_metadata(graph, out_dir: Path) -> dict:
    drawable = graph.get_graph()
    nodes = list(drawable.nodes.keys()) if hasattr(drawable, "nodes") else []
    edges = []
    if hasattr(drawable, "edges"):
        for edge in drawable.edges:
            if isinstance(edge, tuple) and len(edge) >= 2:
                edges.append({"from": edge[0], "to": edge[1]})
            else:
                edges.append({"raw": str(edge)})

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "agent_api/core/graph.py :: build_graph()",
        "entry_point": "agent",
        "conditional_routing": {
            "node": "agent",
            "function": "_route_after_model",
            "branches": {"tools": "tools", "end": "__end__"},
        },
        "linear_edges": [
            "tools -> process_results",
            "process_results -> finalize",
            "finalize -> __end__",
        ],
        "nodes": nodes,
        "edges": edges,
        "node_metadata": NODE_META,
        "post_graph_pipeline": POST_GRAPH,
    }

    meta_path = out_dir / "langgraph-metadata.json"
    meta_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def export_annotated(out_dir: Path) -> dict:
    mmd_path = out_dir / "langgraph-anotado.mmd"
    mmd_path.write_text(ANNOTATED_MERMAID, encoding="utf-8")

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <title>LangGraph — Agente BI (anotado)</title>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
  <style>
    body {{
      margin: 0; font-family: 'Segoe UI', sans-serif;
      background: #0f1419; color: #e2e8f0;
    }}
    header {{
      padding: 1.25rem 2rem;
      background: #3c3c3b;
      border-bottom: 4px solid #f5c418;
    }}
    header h1 {{ margin: 0; color: #fff; font-size: 1.35rem; }}
    header p {{ margin: 0.35rem 0 0; color: #94a3b8; font-size: 0.9rem; }}
    main {{ padding: 2rem; max-width: 1400px; margin: 0 auto; }}
    .panel {{
      background: #1e293b; border-radius: 12px; padding: 1.5rem;
      margin-bottom: 1.5rem; border: 1px solid #334155;
    }}
    .mermaid {{ background: #fff; border-radius: 12px; padding: 1rem; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
    th, td {{ border: 1px solid #334155; padding: 0.6rem 0.75rem; text-align: left; }}
    th {{ background: #0496cd; color: #fff; }}
    code {{ background: #0f172a; padding: 0.1rem 0.35rem; border-radius: 4px; }}
    .badge {{
      display: inline-block; margin-top: 0.75rem; padding: 0.25rem 0.75rem;
      border-radius: 999px; background: rgba(4,150,205,0.2); color: #7dd3fc;
      font-size: 0.8rem;
    }}
    img {{ max-width: 100%; border-radius: 12px; border: 1px solid #334155; }}
  </style>
</head>
<body>
  <header>
    <h1>LangGraph — Arquitectura generada</h1>
    <p>Generado: {datetime.now().strftime("%d/%m/%Y %H:%M")} · scripts/visualizar_langgraph.py</p>
    <span class="badge">Oficial desde agent_graph.get_graph() + anotaciones del código</span>
  </header>
  <main>
    <section class="panel">
      <h2>Diagrama anotado (Mermaid)</h2>
      <pre class="mermaid">{ANNOTATED_MERMAID.split('---', 2)[2].strip()}</pre>
    </section>
    <section class="panel">
      <h2>PNG oficial LangGraph</h2>
      <p>Exportado con <code>draw_mermaid_png()</code> — refleja el grafo compilado real.</p>
      <img src="langgraph-oficial.png" alt="LangGraph oficial" />
    </section>
    <section class="panel">
      <h2>Nodos del grafo</h2>
      <table>
        <tr><th>Nodo</th><th>Función</th><th>Descripción</th><th>LLM</th></tr>
        <tr><td>agent</td><td><code>call_model()</code></td><td>Genera DAX y tool_calls</td><td>DeepSeek + tools</td></tr>
        <tr><td>tools</td><td><code>_run_tools()</code></td><td>Ejecuta execute_dax_query</td><td>—</td></tr>
        <tr><td>process_results</td><td><code>_process_tool_results()</code></td><td>raw_data + current_dax_query</td><td>—</td></tr>
        <tr><td>finalize</td><td><code>finalize_response()</code></td><td>Narrativa JSON</td><td>DeepSeek</td></tr>
      </table>
    </section>
    <section class="panel">
      <h2>Post-grafo (run_agent, fuera de LangGraph)</h2>
      <table>
        <tr><th>Paso</th><th>Función</th><th>Descripción</th></tr>
        <tr><td>parse</td><td><code>_extract_json_from_text()</code></td><td>Extrae JSON de la respuesta final</td></tr>
        <tr><td>build</td><td><code>_build_agent_response()</code></td><td>Arma dict de respuesta API</td></tr>
        <tr><td>chart</td><td><code>ensure_echarts_config()</code></td><td>Infere gráfico ECharts</td></tr>
      </table>
    </section>
  </main>
  <script>mermaid.initialize({{
    startOnLoad: true,
    theme: 'default',
    securityLevel: 'loose',
    flowchart: {{ htmlLabels: true, curve: 'basis' }},
  }});</script>
</body>
</html>
"""
    html_path = out_dir / "langgraph-anotado.html"
    html_path.write_text(html, encoding="utf-8")

    return {
        "mermaid": str(mmd_path.relative_to(ROOT)),
        "html": str(html_path.relative_to(ROOT)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Visualiza el grafo LangGraph del agente BI")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUT,
        help="Directorio de salida para diagramas",
    )
    parser.add_argument("--no-open", action="store_true", help="No abrir el HTML al finalizar")
    args = parser.parse_args()

    out_dir = ensure_output_dir(args.output.resolve())
    print(f"Exportando grafo LangGraph -> {out_dir}")

    graph = load_compiled_graph()
    official = export_official(graph, out_dir)
    metadata = export_metadata(graph, out_dir)
    annotated = export_annotated(out_dir)

    print("\n--- ASCII (resumen) ---")
    print((out_dir / "langgraph-ascii.txt").read_text(encoding="utf-8"))

    print("\nArchivos generados:")
    for key, path in {**official, **annotated}.items():
        if key != "png_bytes":
            print(f"  - {path}")
    print(f"  - {out_dir / 'langgraph-metadata.json'}")

    print(f"\nPNG oficial: {official['png_bytes']:,} bytes")
    print(f"Nodos detectados: {', '.join(metadata.get('nodes', []))}")
    print(f"\nAbrir visor: {annotated['html']}")

    if not args.no_open:
        import webbrowser
        webbrowser.open((out_dir / "langgraph-anotado.html").as_uri())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
