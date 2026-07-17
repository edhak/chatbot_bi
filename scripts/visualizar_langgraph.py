#!/usr/bin/env python3
"""
Visualiza el grafo LangGraph compilado del agente BI (pipeline multi-agente).

Uso:
    python scripts/visualizar_langgraph.py --no-open
    python scripts/visualizar_langgraph.py --png-remote   # intenta mermaid.ink (requiere red)

Salidas en documentacion/imagenes/langgraph-generado/:
    - langgraph-oficial.mmd / .png
    - langgraph-anotado.mmd / .html
    - langgraph-pipeline.png   (PNG local, sin internet)
    - langgraph-metadata.json
    - langgraph-ascii.txt
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "documentacion" / "imagenes" / "langgraph-generado"
STATIC_SVG = ROOT / "documentacion" / "imagenes" / "langgraph-flujo.svg"

NODE_META = {
    "dax_translator_agent": {
        "function": "dax_translator_agent()",
        "description": "Experto DAX: genera generated_dax (lookup filtros + diccionario cubo)",
        "llm": "get_llm() · DeepSeek",
    },
    "execute_dax_node": {
        "function": "execute_dax_node()",
        "description": "Ejecuta DAX en SSAS/mock; actualiza dax_execution_result y dax_retries",
        "llm": None,
    },
    "data_profiler_agent": {
        "function": "data_profiler_agent()",
        "description": "Perfila forma de datos -> data_profile_summary",
        "llm": None,
    },
    "visualization_agent": {
        "function": "visualization_agent()",
        "description": "Elige grafico ECharts -> chart_configuration",
        "llm": "get_llm() · DeepSeek (opcional)",
    },
    "narrative_agent": {
        "function": "narrative_agent()",
        "description": "Narrativa ejecutiva -> response_text",
        "llm": "get_llm() · DeepSeek",
    },
    "error_response": {
        "function": "error_response_node()",
        "description": "Tras agotar MAX_DAX_RETRIES: mensaje de error al usuario",
        "llm": None,
    },
}

POST_GRAPH = [
    {
        "step": "build",
        "function": "_build_api_response()",
        "description": "Ensambla payload API desde el estado del pipeline",
    },
]

# Mermaid sin caracteres especiales (evita "Syntax error in text" en Mermaid 11)
ANNOTATED_MERMAID = """---
title: Agente BI - Pipeline multi-agente LangGraph
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

    START(["__start__ / run_agent"]):::startEnd
    DAX["dax_translator_agent<br/>NL a DAX + lookup"]:::agent
    EXEC["execute_dax_node<br/>SSAS / mock"]:::tool
    ROUTE{"DAX OK?<br/>route_after_execute"}:::decision
    PROF["data_profiler_agent<br/>data_profile_summary"]:::process
    VIZ["visualization_agent<br/>chart_configuration"]:::finalize
    NAR["narrative_agent<br/>response_text"]:::finalize
    ERR["error_response<br/>reintentos agotados"]:::warn
    ENDG(["__end__"]):::startEnd
    BUILD["build<br/>_build_api_response"]:::post
    API["QueryResponse API"]:::startEnd

    START --> DAX --> EXEC --> ROUTE
    ROUTE -->|"error retries menor MAX"| DAX
    ROUTE -->|"error retries mayor igual MAX"| ERR
    ROUTE -->|ok| PROF --> VIZ --> NAR --> ENDG
    ERR --> ENDG
    ENDG --> BUILD --> API

    subgraph STATE["AgentState"]
        direction LR
        S1[user_query]
        S2[generated_dax]
        S3[dax_execution_result]
        S4[dax_retries]
        S5[data_profile_summary]
        S6[chart_configuration]
        S7[response_text]
    end
"""


def ensure_output_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_compiled_graph():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    # Evitar importar un agent_api viejo instalado en site-packages
    for key in list(sys.modules):
        if key == "agent_api" or key.startswith("agent_api."):
            del sys.modules[key]
    from agent_api.core.graph import agent_graph

    return agent_graph


def render_pipeline_png(out_path: Path) -> int:
    """Dibuja el pipeline multi-agente en PNG local (sin internet)."""
    from PIL import Image, ImageDraw, ImageFont

    w, h = 1400, 780
    img = Image.new("RGB", (w, h), "#0f1419")
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype("segoeui.ttf", 28)
        font = ImageFont.truetype("segoeui.ttf", 14)
        font_sm = ImageFont.truetype("segoeui.ttf", 12)
    except OSError:
        font_title = ImageFont.load_default()
        font = font_title
        font_sm = font_title

    draw.rectangle([0, 0, w, 6], fill="#f5c418")
    draw.text((w // 2, 24), "LangGraph — Pipeline multi-agente", fill="#ffffff", font=font_title, anchor="mt")
    draw.text(
        (w // 2, 58),
        "dax_translator → execute_dax → profiler → visualization → narrative",
        fill="#94a3b8",
        font=font_sm,
        anchor="mt",
    )

    def box(x, y, bw, bh, fill, title, subtitle, text_color="#ffffff"):
        draw.rounded_rectangle([x, y, x + bw, y + bh], radius=14, fill=fill)
        draw.text((x + bw // 2, y + bh // 2 - 10), title, fill=text_color, font=font, anchor="mm")
        draw.text((x + bw // 2, y + bh // 2 + 14), subtitle, fill=text_color, font=font_sm, anchor="mm")

    def arrow(x1, y1, x2, y2, color="#0496cd"):
        draw.line([(x1, y1), (x2, y2)], fill=color, width=3)
        # punta simple
        draw.polygon([(x2, y2), (x2 - 10, y2 - 6), (x2 - 10, y2 + 6)], fill=color)

    y = 140
    # fila principal
    box(40, y, 120, 80, "#1e293b", "START", "run_agent", "#7dd3fc")
    box(200, y, 200, 80, "#0496cd", "dax_translator", "NL → DAX + lookup")
    box(440, y, 180, 80, "#f5c418", "execute_dax", "SSAS / mock", "#1a1a19")
    # decision
    cx, cy = 720, y + 40
    draw.polygon([(cx, cy - 40), (cx + 55, cy), (cx, cy + 40), (cx - 55, cy)], fill="#1e293b", outline="#f5c418")
    draw.text((cx, cy - 8), "DAX OK?", fill="#f5c418", font=font_sm, anchor="mm")
    draw.text((cx, cy + 12), "retries?", fill="#94a3b8", font=font_sm, anchor="mm")

    box(820, y, 180, 80, "#10b981", "data_profiler", "metadatos")
    box(1040, y, 180, 80, "#8b5cf6", "visualization", "ECharts")

    arrow(160, y + 40, 198, y + 40)
    arrow(400, y + 40, 438, y + 40)
    arrow(620, y + 40, 665, y + 40)
    arrow(775, y + 40, 818, y + 40, "#10b981")
    arrow(1000, y + 40, 1038, y + 40, "#8b5cf6")
    draw.text((790, y - 8), "ok", fill="#10b981", font=font_sm)

    # retry loop
    draw.arc([220, 80, 700, 200], start=200, end=340, fill="#f5c418", width=3)
    draw.text((420, 88), "retry → translator", fill="#f5c418", font=font_sm)

    # error + narrative + end
    box(640, 320, 160, 70, "#1e293b", "error_response", "retries >= MAX", "#ef4444")
    arrow(720, y + 80, 720, 318, "#ef4444")

    box(1040, 280, 180, 70, "#8b5cf6", "narrative", "response_text")
    arrow(1130, y + 80, 1130, 278, "#8b5cf6")

    box(1040, 400, 180, 70, "#1e293b", "END", "QueryResponse", "#7dd3fc")
    arrow(1130, 350, 1130, 398)

    # state panel
    draw.rounded_rectangle([40, 280, 360, 520], radius=12, outline="#334155", width=2)
    draw.text((200, 300), "AgentState", fill="#f5c418", font=font, anchor="mt")
    states = [
        "user_query",
        "generated_dax",
        "dax_execution_result",
        "dax_retries",
        "data_profile_summary",
        "chart_configuration",
        "response_text",
    ]
    for i, name in enumerate(states):
        draw.text((60, 340 + i * 24), f"• {name}", fill="#94a3b8", font=font_sm)

    # legend
    draw.rounded_rectangle([400, 420, 900, 560], radius=12, outline="#334155", width=2)
    draw.text((420, 440), "Leyenda", fill="#ffffff", font=font)
    legend = [
        ("#0496cd", "Traductor DAX (LLM + diccionario cubo)"),
        ("#f5c418", "Ejecucion SSAS / mock"),
        ("#10b981", "Profiler de metadatos"),
        ("#8b5cf6", "Visualizacion + narrativa"),
    ]
    for i, (color, label) in enumerate(legend):
        yy = 470 + i * 22
        draw.rectangle([420, yy, 436, yy + 14], fill=color)
        draw.text((448, yy), label, fill="#94a3b8", font=font_sm)

    draw.text(
        (w // 2, h - 30),
        "Generado localmente · scripts/visualizar_langgraph.py · sin mermaid.ink",
        fill="#64748b",
        font=font_sm,
        anchor="mt",
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    # copiar tambien a langgraph-flujo.png y oficial si se pide
    return out_path.stat().st_size


def export_official(graph, out_dir: Path, *, try_remote_png: bool) -> dict:
    drawable = graph.get_graph()

    mermaid = drawable.draw_mermaid()
    mmd_path = out_dir / "langgraph-oficial.mmd"
    mmd_path.write_text(mermaid, encoding="utf-8")

    ascii_path = out_dir / "langgraph-ascii.txt"
    try:
        ascii_art = drawable.draw_ascii()
    except Exception:
        ascii_art = "\n".join(
            [
                "Pipeline multi-agente:",
                "  dax_translator_agent -> execute_dax_node",
                "    |-- ok -> data_profiler_agent -> visualization_agent -> narrative_agent",
                "    |-- error & retries < MAX -> dax_translator_agent",
                "    |-- error & retries >= MAX -> error_response",
            ]
        )
    ascii_path.write_text(str(ascii_art), encoding="utf-8")

    # PNG local siempre (Pillow)
    local_png = out_dir / "langgraph-pipeline.png"
    png_bytes = 0
    try:
        png_bytes = render_pipeline_png(local_png)
        # Actualizar oficial.png con el diagrama local (visible sin red)
        oficial = out_dir / "langgraph-oficial.png"
        oficial.write_bytes(local_png.read_bytes())
        flujo_png = ROOT / "documentacion" / "imagenes" / "langgraph-flujo.png"
        flujo_png.write_bytes(local_png.read_bytes())
    except Exception as exc:
        return {
            "mermaid": str(mmd_path.relative_to(ROOT)),
            "ascii": str(ascii_path.relative_to(ROOT)),
            "png": str(local_png.relative_to(ROOT)),
            "png_bytes": 0,
            "png_warning": f"No se pudo generar PNG local: {exc}",
        }

    png_warning = None
    if try_remote_png:
        try:
            remote = drawable.draw_mermaid_png(max_retries=2, retry_delay=1.0)
            remote_path = out_dir / "langgraph-oficial-remote.png"
            remote_path.write_bytes(remote)
        except Exception as exc:
            png_warning = f"PNG remoto (mermaid.ink) no disponible: {str(exc)[:160]}"

    result = {
        "mermaid": str(mmd_path.relative_to(ROOT)),
        "png": str((out_dir / "langgraph-oficial.png").relative_to(ROOT)),
        "pipeline_png": str(local_png.relative_to(ROOT)),
        "ascii": str(ascii_path.relative_to(ROOT)),
        "png_bytes": png_bytes,
    }
    if png_warning:
        result["png_warning"] = png_warning
    return result


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
        "entry_point": "dax_translator_agent",
        "conditional_routing": {
            "node": "execute_dax_node",
            "function": "_route_after_execute",
            "branches": {
                "dax_translator_agent": "retry DAX",
                "data_profiler_agent": "success",
                "error_response": "max retries",
            },
        },
        "linear_edges": [
            "dax_translator_agent -> execute_dax_node",
            "data_profiler_agent -> visualization_agent",
            "visualization_agent -> narrative_agent",
            "narrative_agent -> __end__",
            "error_response -> __end__",
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

    # Cuerpo mermaid (sin frontmatter YAML) para el HTML
    mermaid_body = ANNOTATED_MERMAID.split("---", 2)[-1].strip()

    svg_embed = ""
    if STATIC_SVG.exists():
        raw = STATIC_SVG.read_bytes()
        for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
            try:
                svg_embed = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            svg_embed = raw.decode("utf-8", errors="replace")

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <title>LangGraph — Pipeline multi-agente BI</title>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
  <style>
    body {{ margin: 0; font-family: 'Segoe UI', sans-serif; background: #0f1419; color: #e2e8f0; }}
    header {{ padding: 1.25rem 2rem; background: #3c3c3b; border-bottom: 4px solid #f5c418; }}
    header h1 {{ margin: 0; color: #fff; font-size: 1.35rem; }}
    header p {{ margin: 0.35rem 0 0; color: #94a3b8; font-size: 0.9rem; }}
    main {{ padding: 2rem; max-width: 1400px; margin: 0 auto; }}
    .panel {{ background: #1e293b; border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; border: 1px solid #334155; }}
    .mermaid {{ background: #fff; border-radius: 12px; padding: 1rem; }}
    .svg-wrap {{ background: #0f1419; border-radius: 12px; overflow: auto; }}
    .svg-wrap svg {{ width: 100%; height: auto; display: block; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
    th, td {{ border: 1px solid #334155; padding: 0.6rem 0.75rem; text-align: left; }}
    th {{ background: #0496cd; color: #fff; }}
    code {{ background: #0f172a; padding: 0.1rem 0.35rem; border-radius: 4px; }}
    .badge {{ display: inline-block; margin-top: 0.75rem; padding: 0.25rem 0.75rem; border-radius: 999px;
      background: rgba(4,150,205,0.2); color: #7dd3fc; font-size: 0.8rem; }}
    img {{ max-width: 100%; border-radius: 12px; border: 1px solid #334155; }}
    .err {{ color: #fca5a5; font-size: 0.9rem; }}
  </style>
</head>
<body>
  <header>
    <h1>LangGraph — Pipeline multi-agente</h1>
    <p>Generado: {datetime.now().strftime("%d/%m/%Y %H:%M")} · scripts/visualizar_langgraph.py</p>
    <span class="badge">dax_translator → execute → profiler → visualization → narrative</span>
  </header>
  <main>
    <section class="panel">
      <h2>1. Diagrama PNG (local, siempre visible)</h2>
      <img src="langgraph-pipeline.png" alt="Pipeline multi-agente" />
      <p style="margin-top:0.75rem;color:#94a3b8;font-size:0.85rem">
        Archivo: <code>langgraph-pipeline.png</code> / <code>langgraph-oficial.png</code>
      </p>
    </section>

    <section class="panel">
      <h2>2. SVG anotado</h2>
      <div class="svg-wrap">
{svg_embed if svg_embed else '<p class="err">No se encontro langgraph-flujo.svg</p>'}
      </div>
    </section>

    <section class="panel">
      <h2>3. Mermaid (requiere CDN / red)</h2>
      <pre class="mermaid">
{mermaid_body}
      </pre>
      <p id="mermaid-status" class="err" style="display:none;margin-top:0.75rem">
        Si este bloque sale vacio o con error, use el PNG de la seccion 1 (no necesita internet).
      </p>
    </section>

    <section class="panel">
      <h2>Nodos del pipeline</h2>
      <table>
        <tr><th>Nodo</th><th>Funcion</th><th>Descripcion</th><th>LLM</th></tr>
        <tr><td>dax_translator_agent</td><td><code>dax_translator_agent()</code></td><td>Genera DAX + lookup filtros</td><td>DeepSeek</td></tr>
        <tr><td>execute_dax_node</td><td><code>execute_dax_node()</code></td><td>Ejecuta DAX / reintentos</td><td>—</td></tr>
        <tr><td>data_profiler_agent</td><td><code>data_profiler_agent()</code></td><td>Perfil de metadatos</td><td>—</td></tr>
        <tr><td>visualization_agent</td><td><code>visualization_agent()</code></td><td>Elige grafico ECharts</td><td>DeepSeek opcional</td></tr>
        <tr><td>narrative_agent</td><td><code>narrative_agent()</code></td><td>Narrativa ejecutiva</td><td>DeepSeek</td></tr>
        <tr><td>error_response</td><td><code>error_response_node()</code></td><td>Error tras MAX retries</td><td>—</td></tr>
      </table>
    </section>
  </main>
  <script>
    try {{
      mermaid.initialize({{
        startOnLoad: true,
        theme: 'default',
        securityLevel: 'loose',
        flowchart: {{ htmlLabels: true, curve: 'basis' }},
      }});
    }} catch (e) {{
      document.getElementById('mermaid-status').style.display = 'block';
    }}
    setTimeout(function() {{
      var el = document.querySelector('.mermaid svg');
      if (!el) {{
        var s = document.getElementById('mermaid-status');
        if (s) s.style.display = 'block';
      }}
    }}, 2500);
  </script>
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
    parser = argparse.ArgumentParser(description="Visualiza el grafo LangGraph multi-agente")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT, help="Directorio de salida")
    parser.add_argument("--no-open", action="store_true", help="No abrir el HTML al finalizar")
    parser.add_argument(
        "--png-remote",
        action="store_true",
        help="Intentar tambien PNG via mermaid.ink (requiere red; suele fallar en VPN)",
    )
    args = parser.parse_args()

    out_dir = ensure_output_dir(args.output.resolve())
    print(f"Exportando grafo LangGraph -> {out_dir}")

    graph = load_compiled_graph()
    nodes = list(graph.get_graph().nodes.keys())
    print(f"Nodos del grafo compilado: {', '.join(nodes)}")

    expected = {
        "dax_translator_agent",
        "execute_dax_node",
        "data_profiler_agent",
        "visualization_agent",
        "narrative_agent",
    }
    missing = expected - set(nodes)
    if missing:
        print(f"ERROR: el grafo no es multi-agente. Faltan: {sorted(missing)}")
        print("Verifique que agent_api/core/graph.py este actualizado.")
        return 1

    official = export_official(graph, out_dir, try_remote_png=args.png_remote)
    metadata = export_metadata(graph, out_dir)
    annotated = export_annotated(out_dir)

    print("\n--- ASCII ---")
    print((out_dir / "langgraph-ascii.txt").read_text(encoding="utf-8"))

    print("\nArchivos generados:")
    for key, path in {**official, **annotated}.items():
        if key in ("png_bytes", "png_warning"):
            continue
        print(f"  - {path}")
    print(f"  - {out_dir / 'langgraph-metadata.json'}")

    print(f"\nPNG local: {official.get('png_bytes', 0):,} bytes")
    if official.get("png_warning"):
        print(f"AVISO: {official['png_warning']}")

    html_uri = (out_dir / "langgraph-anotado.html").as_uri()
    print(f"\nAbrir visor:\n  {html_uri}")

    if not args.no_open:
        import webbrowser

        webbrowser.open(html_uri)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
