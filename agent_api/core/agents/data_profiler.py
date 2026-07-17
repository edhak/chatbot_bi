"""
Agente profiler: resume la forma de los datos sin alterar valores.
"""

from __future__ import annotations

import time
from typing import Any

from agent_api.core.agents.llm_utils import get_trace, rows_from_execution_result
from agent_api.core.chart_selector import profile_data
from agent_api.core.state import AgentState


def _format_profile_summary(rows: list[dict[str, Any]]) -> str:
    profile = profile_data(rows)
    lines = [
        f"Filas: {profile.row_count}",
        f"Dimensiones: {', '.join(profile.text_columns) or '(ninguna)'}",
        f"Medidas: {', '.join(profile.numeric_columns) or '(ninguna)'}",
        f"Columna categoría principal: {profile.category_column or '(n/a)'}",
        f"Cardinalidad de categorías: {profile.category_count}",
        f"Longitud máxima de etiqueta: {profile.max_label_length}",
        f"Serie temporal: {'sí' if profile.is_time_series else 'no'}",
        f"Secuencia ordenada: {'sí' if profile.is_ordered_sequence else 'no'}",
        f"KPI valor único: {'sí' if profile.is_single_value else 'no'}",
        f"Múltiples medidas: {'sí' if profile.has_multiple_measures else 'no'}",
        f"Valores positivos: {'sí' if profile.all_values_positive else 'no'}",
    ]
    if profile.categories:
        preview = ", ".join(profile.categories[:8])
        if len(profile.categories) > 8:
            preview += ", ..."
        lines.append(f"Muestra de categorías: {preview}")
    return "\n".join(lines)


def data_profiler_agent(state: AgentState) -> dict[str, Any]:
    """Analiza metadatos de dax_execution_result y escribe data_profile_summary."""
    trace = get_trace(state)
    trace.log("data_profiler", "Perfilando estructura de datos...")
    t0 = time.perf_counter()

    rows = rows_from_execution_result(state.get("dax_execution_result"))
    if not rows:
        rows = state.get("raw_data") or []

    summary = _format_profile_summary(rows)
    elapsed = int((time.perf_counter() - t0) * 1000)
    trace.log("data_profiler", f"Perfil listo en {elapsed}ms — {len(rows)} filas")

    return {
        "data_profile_summary": summary,
        "raw_data": rows,
        "_trace": trace,
    }
