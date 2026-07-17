"""Verifica que visualización + narrativa producen texto y gráfico."""
from __future__ import annotations

import os

os.environ.setdefault("SSAS_USE_MOCK", "true")
os.environ.setdefault("DEEPSEEK_API_KEY", os.getenv("DEEPSEEK_API_KEY", "sk-test"))

from agent_api.core.agents.narrative import error_response_node, narrative_agent
from agent_api.core.agents.visualization import visualization_agent
from agent_api.core.chart_builder import has_valid_chart
from agent_api.core.debug_log import AgentDebugTrace


def main() -> None:
    rows = [
        {"Region_Destino": "CALIFORNIA", "Total": 120},
        {"Region_Destino": "TEXAS", "Total": 90},
        {"Region_Destino": "FLORIDA", "Total": 70},
    ]
    trace = AgentDebugTrace()
    state = {
        "user_query": "regiones en estados unidos",
        "generated_dax": 'EVALUATE ROW("x", 1)',
        "dax_execution_result": {"ok": True, "rows": rows},
        "raw_data": rows,
        "data_profile_summary": "Filas: 3\nMedidas: Total",
        "chart_configuration": {},
        "dax_retries": 0,
        "_trace": trace,
    }

    viz = visualization_agent(state)
    state.update(viz)
    chart = viz.get("chart_configuration") or {}
    assert has_valid_chart(chart), "visualización no generó gráfico válido"
    print("viz_ok", chart.get("chart_meta", {}).get("selected_type"))

    nar = narrative_agent(state)
    text = nar.get("response_text") or ""
    assert text.strip(), "narrativa vacía"
    assert has_valid_chart(nar.get("chart_configuration")), "narrativa perdió el gráfico"
    print("narrative_ok", len(text), "chars")

    err = error_response_node(
        {
            "dax_execution_result": {"ok": False, "error": "sin filas"},
            "generated_dax": 'EVALUATE ROW("a", 1)',
            "dax_retries": 3,
            "validation_error": "",
            "_trace": trace,
        }
    )
    assert "Detalle" in err["response_text"]
    assert not has_valid_chart(err.get("chart_configuration"))
    print("error_path_ok")
    print("ALL_OK")


if __name__ == "__main__":
    main()
