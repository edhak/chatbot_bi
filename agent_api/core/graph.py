"""
Grafo LangGraph multi-agente (pipeline) para el agente analítico BI.

Flujo:
  __start__
    → dax_translator_agent
    → execute_dax_node
    → (retry → dax_translator | error | data_profiler)
    → visualization_agent
    → narrative_agent
    → __end__
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Literal

from langgraph.graph import END, StateGraph

from agent_api.core.agents import (
    data_profiler_agent,
    dax_translator_agent,
    error_response_node,
    execute_dax_node,
    narrative_agent,
    visualization_agent,
)
from agent_api.core.agents.llm_utils import get_trace, rows_from_execution_result, sanitize_dax_query
from agent_api.core.chart_builder import has_valid_chart
from agent_api.core.debug_log import AgentDebugTrace, is_debug_enabled
from agent_api.core.state import AgentState

MAX_DAX_RETRIES = int(os.getenv("MAX_DAX_RETRIES", "3"))


def _json_safe(value: Any) -> Any:
    """Garantiza que echarts_config / payloads sean serializables a JSON."""
    try:
        return json.loads(json.dumps(value, default=str, ensure_ascii=False))
    except Exception:
        return {}


def _route_after_execute(
    state: AgentState,
) -> Literal["dax_translator_agent", "data_profiler_agent", "error_response"]:
    result = state.get("dax_execution_result") or {}
    ok = bool(result.get("ok")) and bool(rows_from_execution_result(result))
    trace = get_trace(state)
    if ok:
        trace.log("route", "execute_dax -> data_profiler_agent")
        return "data_profiler_agent"

    retries = int(state.get("dax_retries", 0))
    if retries < MAX_DAX_RETRIES:
        trace.log(
            "route",
            f"execute_dax -> dax_translator_agent (retry {retries}/{MAX_DAX_RETRIES})",
        )
        return "dax_translator_agent"
    trace.log("route", f"execute_dax -> error_response (retries={retries})")
    return "error_response"


def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("dax_translator_agent", dax_translator_agent)
    workflow.add_node("execute_dax_node", execute_dax_node)
    workflow.add_node("data_profiler_agent", data_profiler_agent)
    workflow.add_node("visualization_agent", visualization_agent)
    workflow.add_node("narrative_agent", narrative_agent)
    workflow.add_node("error_response", error_response_node)

    workflow.set_entry_point("dax_translator_agent")
    workflow.add_edge("dax_translator_agent", "execute_dax_node")
    workflow.add_conditional_edges(
        "execute_dax_node",
        _route_after_execute,
        {
            "dax_translator_agent": "dax_translator_agent",
            "data_profiler_agent": "data_profiler_agent",
            "error_response": "error_response",
        },
    )
    workflow.add_edge("data_profiler_agent", "visualization_agent")
    workflow.add_edge("visualization_agent", "narrative_agent")
    workflow.add_edge("narrative_agent", END)
    workflow.add_edge("error_response", END)

    return workflow.compile()


agent_graph = build_graph()


def _build_api_response(
    *,
    text_response: str,
    dax_query: str,
    raw_data: list[dict[str, Any]],
    chart_config: dict[str, Any],
    trace: AgentDebugTrace,
) -> dict[str, Any]:
    has_chart = has_valid_chart(chart_config) if isinstance(chart_config, dict) else False
    meta = chart_config.get("chart_meta") if isinstance(chart_config, dict) else None
    if isinstance(meta, dict):
        trace.log(
            "chart_select",
            f"{meta.get('selected_label')} ({meta.get('selected_type')}) — {meta.get('reason')}",
        )
    trace.log(
        "build_response",
        f"text_len={len(text_response)} dax_len={len(dax_query)} "
        f"raw_rows={len(raw_data)} has_chart={has_chart}",
    )
    return {
        "text_response": text_response or "(Sin texto de respuesta del agente)",
        "dax_query": dax_query,
        "echarts_config": chart_config or {},
        "raw_data": raw_data,
        "debug_log": trace.to_list() if is_debug_enabled() else [],
    }


def run_agent(question: str, cube_address: str) -> dict[str, Any]:
    """Punto de entrada del pipeline multi-agente (contrato API sin cambios)."""
    trace = AgentDebugTrace()
    trace.log("start", f"Pregunta recibida: {question[:100]}")
    trace.log("pipeline", "Arquitectura multi-agente (traductor → execute → profiler → viz)")

    initial_state: AgentState = {
        "user_query": question,
        "generated_dax": "",
        "dax_execution_result": {},
        "dax_retries": 0,
        "data_profile_summary": "",
        "chart_configuration": {},
        "current_dax_query": "",
        "raw_data": [],
        "echarts_config": {},
        "retry_count": 0,
        "_trace": trace,
    }

    config = {
        "configurable": {"cube_address": cube_address},
        "recursion_limit": int(os.getenv("AGENT_RECURSION_LIMIT", "50")),
    }

    try:
        trace.log("graph", "Ejecutando grafo multi-agente...")
        t0 = time.perf_counter()
        result = agent_graph.invoke(initial_state, config=config)
        trace = result.get("_trace", trace)
        trace.log("graph", f"Grafo completado en {int((time.perf_counter() - t0) * 1000)}ms")
    except Exception as exc:
        trace.log("graph", f"Error en grafo: {exc}", "error")
        return _build_api_response(
            text_response=f"Error interno del agente: {exc}",
            dax_query="",
            raw_data=[],
            chart_config={},
            trace=trace,
        )

    dax_query = (
        result.get("response_dax")
        or result.get("generated_dax")
        or result.get("current_dax_query")
        or ""
    )
    dax_query = sanitize_dax_query(dax_query)
    raw_data = result.get("raw_data") or rows_from_execution_result(
        result.get("dax_execution_result")
    )
    chart_config = result.get("chart_configuration") or result.get("echarts_config") or {}
    if not isinstance(chart_config, dict):
        chart_config = {}
    chart_config = _json_safe(chart_config)
    text_response = result.get("response_text") or "No se pudo generar una respuesta."

    # Si hay datos pero el gráfico se perdió (p. ej. merge de estado), reconstruir
    if raw_data and not has_valid_chart(chart_config):
        try:
            from agent_api.core.chart_builder import ensure_echarts_config
            from agent_api.core.chart_selector import coerce_rows_for_charts

            safe_rows = coerce_rows_for_charts(
                [r for r in raw_data if isinstance(r, dict)]
            )
            chart_config = _json_safe(
                ensure_echarts_config(None, safe_rows, title=(question or "")[:80])
            )
            raw_data = safe_rows
            trace.log(
                "build_response",
                f"Gráfico reconstruido desde raw_data ({len(safe_rows)} filas, "
                f"valid={has_valid_chart(chart_config)})",
                "warn",
            )
        except Exception as exc:
            trace.log("build_response", f"No se pudo reconstruir gráfico: {exc}", "warn")

    return _build_api_response(
        text_response=text_response,
        dax_query=dax_query,
        raw_data=raw_data if isinstance(raw_data, list) else [],
        chart_config=chart_config,
        trace=trace,
    )
