"""
Agente de visualización: perfil + pregunta → chart_configuration ECharts.
"""

from __future__ import annotations

import time
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agent_api.core.agents.llm_utils import get_llm, get_trace, rows_from_execution_result
from agent_api.core.agents.prompts import visualization_prompt
from agent_api.core.chart_builder import build_echarts_from_data, ensure_echarts_config, has_valid_chart
from agent_api.core.chart_selector import (
    CHART_CATALOG,
    ChartRecommendation,
    coerce_rows_for_charts,
    recommend_chart_type,
    score_chart_type,
)
from agent_api.core.state import AgentState

ChartChoice = Literal[
    "bar",
    "bar_horizontal",
    "bar_stacked",
    "line",
    "pie",
    "treemap",
    "heatmap",
    "scatter",
    "radar",
    "gauge",
    "funnel",
    "candlestick",
]


class VisualizationChoice(BaseModel):
    chart_type: ChartChoice = Field(description="Tipo de gráfico del catálogo.")
    reason: str = Field(description="Justificación breve de la elección.")


def _chart_title(user_query: str) -> str:
    title = (user_query or "").strip()
    if not title:
        return "Resultado de la consulta"
    return title[:80]


def visualization_agent(state: AgentState) -> dict[str, Any]:
    """
    Elige el gráfico óptimo con reglas (chart_selector) y opcionalmente
    confirma/ajusta con LLM restringido al catálogo.
    """
    trace = get_trace(state)
    trace.log("visualization", "Seleccionando tipo de gráfico...")
    t0 = time.perf_counter()

    rows = rows_from_execution_result(state.get("dax_execution_result"))
    if not rows:
        rows = state.get("raw_data") or []
    rows = coerce_rows_for_charts(rows)

    user_query = state.get("user_query", "")
    profile_summary = state.get("data_profile_summary", "")
    recommendation = recommend_chart_type(rows)

    chosen_type = recommendation.chart_type
    reason = recommendation.reason
    rule_score = recommendation.confidence

    # LLM opcional: solo si la regla no es clara (evita fallos/latencia innecesaria)
    if rule_score < 0.85:
        try:
            structured = get_llm(max_tokens=300).with_structured_output(VisualizationChoice)
            choice: VisualizationChoice = structured.invoke(
                [
                    SystemMessage(content=visualization_prompt()),
                    HumanMessage(
                        content=(
                            f"Pregunta del usuario:\n{user_query}\n\n"
                            f"Perfil de datos:\n{profile_summary}\n\n"
                            f"Recomendación automática: {recommendation.chart_type} "
                            f"(score={recommendation.confidence}) — {recommendation.reason}\n"
                            "Elige el mejor tipo del catálogo."
                        )
                    ),
                ]
            )
            if choice.chart_type in CHART_CATALOG:
                llm_score, llm_reason = score_chart_type(choice.chart_type, rows)
                min_acceptable = max(0.5, rule_score - 0.12)
                if llm_score >= min_acceptable:
                    chosen_type = choice.chart_type  # type: ignore[assignment]
                    reason = choice.reason or llm_reason
                    rule_score = round(llm_score, 2)
                    trace.log(
                        "visualization",
                        f"LLM eligió {chosen_type} (score={llm_score:.2f}): {reason[:120]}",
                    )
                else:
                    trace.log(
                        "visualization",
                        f"LLM rechazado: {choice.chart_type} score={llm_score:.2f} "
                        f"< mínimo {min_acceptable:.2f}; uso {recommendation.chart_type}",
                        "warn",
                    )
        except Exception as exc:
            trace.log("visualization", f"LLM viz falló, uso reglas: {exc}", "warn")
    else:
        trace.log(
            "visualization",
            f"Reglas suficientes ({chosen_type}, score={rule_score}); se omite LLM",
        )

    rec = ChartRecommendation(
        chart_type=chosen_type,  # type: ignore[arg-type]
        confidence=rule_score,
        reason=reason,
        alternatives=recommendation.alternatives,
    )

    chart_config = build_echarts_from_data(
        rows,
        title=_chart_title(user_query),
        recommendation=rec,
    )
    if not chart_config:
        chart_config = ensure_echarts_config(None, rows, title=_chart_title(user_query))

    # Normalización final (leyenda, tipos soportados)
    chart_config = ensure_echarts_config(chart_config, rows, title=_chart_title(user_query))

    if not has_valid_chart(chart_config):
        # Último recurso: barras simples categoría×primera medida detectable
        chart_config = _emergency_bar_chart(rows, _chart_title(user_query), reason)
        trace.log("visualization", "Fallback de emergencia a barras", "warn")

    meta = chart_config.get("chart_meta") if isinstance(chart_config, dict) else None
    if isinstance(meta, dict):
        meta["selected_type"] = chart_config.get("chart_meta", {}).get("selected_type", chosen_type)
        meta["selected_label"] = CHART_CATALOG.get(
            str(meta.get("selected_type", chosen_type)), {}
        ).get("label", chosen_type)
        meta["reason"] = reason
        chart_config["chart_meta"] = meta

    elapsed = int((time.perf_counter() - t0) * 1000)
    selected = (chart_config.get("chart_meta") or {}).get("selected_type", chosen_type)
    label = CHART_CATALOG.get(str(selected), {}).get("label", selected)
    series_len = 0
    series = chart_config.get("series") if isinstance(chart_config, dict) else None
    if isinstance(series, list) and series:
        series_len = len(series[0].get("data") or []) if isinstance(series[0], dict) else len(series)
    trace.log(
        "visualization",
        f"{label} ({selected}) en {elapsed}ms — series_points={series_len} — {reason[:100]}",
    )

    return {
        "chart_configuration": chart_config,
        "echarts_config": chart_config,
        "raw_data": rows,
        "_trace": trace,
    }


def _emergency_bar_chart(
    rows: list[dict[str, Any]],
    title: str,
    reason: str,
) -> dict[str, Any]:
    """Construye un bar chart mínimo cuando el builder principal falla."""
    if not rows:
        return {}
    keys = list(rows[0].keys())
    text_cols: list[str] = []
    num_cols: list[str] = []
    for key in keys:
        vals = [r.get(key) for r in rows]
        if any(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
            num_cols.append(key)
        else:
            text_cols.append(key)
    if not num_cols:
        return {}
    measure = num_cols[0]
    if text_cols:
        cats = [str(r.get(text_cols[0], "")) for r in rows]
        data = [float(r.get(measure) or 0) for r in rows]
        return {
            "title": {"text": title, "left": "center", "top": 8},
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category", "data": cats},
            "yAxis": {"type": "value"},
            "series": [{"name": measure, "type": "bar", "data": data}],
            "chart_meta": {
                "selected_type": "bar",
                "selected_label": "Barras verticales",
                "reason": f"{reason} (fallback emergencia)",
            },
        }
    return {
        "title": {"text": title, "left": "center", "top": 8},
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "category", "data": [measure]},
        "yAxis": {"type": "value"},
        "series": [
            {
                "name": measure,
                "type": "bar",
                "data": [float(rows[0].get(measure) or 0)],
            }
        ],
        "chart_meta": {
            "selected_type": "bar",
            "selected_label": "Barras verticales",
            "reason": f"{reason} (fallback emergencia)",
        },
    }
