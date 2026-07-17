"""
Agente narrativo: resume hallazgos para el usuario final.
"""

from __future__ import annotations

import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agent_api.core.agents.llm_utils import (
    get_llm,
    get_trace,
    message_content_to_str,
    rows_from_execution_result,
    sanitize_dax_query,
    summarize_rows_compact,
)
from agent_api.core.agents.prompts import narrative_prompt
from agent_api.core.state import AgentState


class NarrativeOutput(BaseModel):
    text_response: str = Field(description="Narrativa ejecutiva breve en Markdown.")


def _fallback_narrative(user_query: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return (
            f"No hay filas para responder: {user_query}\n\n"
            "Revise filtros o reformule la pregunta."
        )
    sample = summarize_rows_compact(rows, max_rows=5)
    return (
        f"Se obtuvieron **{len(rows)}** filas para: {user_query}\n\n"
        f"Muestra de datos:\n```\n{sample}\n```\n\n"
        "Revise el gráfico para el detalle visual."
    )


def narrative_agent(state: AgentState) -> dict[str, Any]:
    """Genera response_text a partir de la pregunta y los datos."""
    trace = get_trace(state)
    trace.log("narrative", "Generando respuesta ejecutiva...")
    t0 = time.perf_counter()

    rows = rows_from_execution_result(state.get("dax_execution_result"))
    if not rows:
        rows = state.get("raw_data") or []

    dax = sanitize_dax_query(
        state.get("generated_dax") or state.get("current_dax_query") or ""
    )
    user_query = state.get("user_query", "")
    profile = state.get("data_profile_summary", "")
    chart_meta = {}
    cfg = state.get("chart_configuration") or {}
    if isinstance(cfg, dict):
        chart_meta = cfg.get("chart_meta") or {}

    prompt_msgs = [
        SystemMessage(content=narrative_prompt()),
        HumanMessage(
            content=(
                f"Pregunta:\n{user_query}\n\n"
                f"Perfil:\n{profile}\n\n"
                f"Gráfico elegido: {chart_meta.get('selected_label', 'n/a')} "
                f"— {chart_meta.get('reason', '')}\n\n"
                f"Datos:\n{summarize_rows_compact(rows)}\n"
            )
        ),
    ]

    text = ""
    try:
        structured = get_llm(max_tokens=800).with_structured_output(NarrativeOutput)
        parsed: NarrativeOutput = structured.invoke(prompt_msgs)
        text = (parsed.text_response or "").strip()
    except Exception as exc:
        trace.log("narrative", f"Structured falló, intento texto libre: {exc}", "warn")
        try:
            raw = get_llm(max_tokens=800).invoke(prompt_msgs)
            text = message_content_to_str(getattr(raw, "content", "")).strip()
        except Exception as exc2:
            trace.log("narrative", f"Texto libre falló: {exc2}", "warn")
            text = ""

    if not text or text.startswith("EVALUATE"):
        text = _fallback_narrative(user_query, rows)

    elapsed = int((time.perf_counter() - t0) * 1000)
    trace.log("narrative", f"Narrativa lista en {elapsed}ms ({len(text)} chars)")

    return {
        "response_text": text,
        "response_dax": dax,
        # Mantener gráfico ya generado por visualization_agent
        "chart_configuration": cfg if isinstance(cfg, dict) else {},
        "echarts_config": cfg if isinstance(cfg, dict) else {},
        "raw_data": rows,
        "_trace": trace,
    }


def error_response_node(state: AgentState) -> dict[str, Any]:
    """Respuesta de error tras agotar reintentos DAX."""
    from agent_api.core.agents.llm_utils import compact_execution_error

    trace = get_trace(state)
    result = state.get("dax_execution_result") or {}
    err = result.get("error") or state.get("validation_error") or "No se obtuvieron datos del cubo."
    dax = sanitize_dax_query(state.get("generated_dax") or "")
    retries = state.get("dax_retries", 0)
    detail = compact_execution_error(str(err), max_len=350)

    text = (
        "No fue posible obtener datos para graficar ni narrar la respuesta.\n\n"
        f"**Intentos fallidos:** {retries}\n\n"
        f"**Detalle:** {detail}\n\n"
        "Sugerencia: reformule la pregunta o acote filtros (país exacto, año, tipo de equipo)."
    )
    if dax:
        text += (
            "\n\nLa consulta DAX generada aparece abajo; falló al ejecutarse en el cubo "
            "(filtros, columnas o 0 filas)."
        )
    trace.log("error_response", f"Error final tras {retries} reintentos — {detail[:160]}", "error")
    return {
        "response_text": text,
        "response_dax": dax,
        "chart_configuration": {},
        "echarts_config": {},
        "raw_data": [],
        "_trace": trace,
    }
