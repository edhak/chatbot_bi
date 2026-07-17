"""
Agente traductor: pregunta NL → consulta DAX (con lookup de filtros).
"""

from __future__ import annotations

import json
import time
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from agent_api.core.agents.llm_utils import (
    compact_execution_error,
    extract_dax_from_text,
    execution_error,
    get_llm,
    get_trace,
    is_valid_dax_structure,
    message_content_to_str,
    sanitize_dax_query,
)
from agent_api.core.agents.prompts import dax_translator_prompt, dax_translator_lookup_prompt
from agent_api.core.state import AgentState
from agent_api.tools.filter_lookup import lookup_dimension_values

LOOKUP_TOOLS = [lookup_dimension_values]
LOOKUP_BY_NAME = {t.name: t for t in LOOKUP_TOOLS}

MAX_LOOKUP_LOOPS = 2
MAX_TOOL_CALLS_PER_ROUND = 2


class DaxOutput(BaseModel):
    dax_query: str = Field(
        description=(
            "ÚNICAMENTE la consulta DAX ejecutable. "
            "Debe empezar con EVALUATE y contener SOLO código DAX. "
            "PROHIBIDO: markdown, ```, explicaciones, notas, rationale, "
            "instrucciones, viñetas o texto en español fuera del DAX."
        )
    )
    rationale: str = Field(
        default="",
        description="Justificación breve en este campo SEPARADO; nunca dentro de dax_query.",
    )


def _tool_args(tc: dict[str, Any]) -> dict[str, Any]:
    args = tc.get("args")
    return args if isinstance(args, dict) else {}


def _sanitize_lookup_args(args: dict[str, Any], user_query: str) -> dict[str, Any]:
    """Copia args y rellena search_hint vacío con la pregunta del usuario."""
    out = dict(args)
    hint = str(out.get("search_hint") or "").strip()
    fallback = (user_query or "").strip()
    if not hint and fallback:
        out["search_hint"] = fallback
    return out


def _run_lookup_tool_calls(
    tool_calls: list[dict[str, Any]],
    *,
    user_query: str,
    config: RunnableConfig,
    trace: Any,
) -> list[ToolMessage]:
    """Ejecuta solo tools permitidas; rechaza el resto con mensaje claro."""
    messages: list[ToolMessage] = []
    for tc in tool_calls:
        name = tc.get("name") or ""
        tc_id = tc.get("id") or name or "unknown"
        if name not in LOOKUP_BY_NAME:
            messages.append(
                ToolMessage(
                    content=json.dumps(
                        {
                            "error": f"Herramienta '{name}' no disponible en dax_translator.",
                            "note": (
                                "Solo existe lookup_dimension_values. "
                                "Tras el lookup, genera el DAX (EVALUATE ...); "
                                "otro nodo del pipeline lo ejecutará."
                            ),
                        },
                        ensure_ascii=False,
                    ),
                    tool_call_id=tc_id,
                    name=name or "unknown",
                )
            )
            continue

        args = _sanitize_lookup_args(_tool_args(tc), user_query)
        trace.log(
            "dax_translator",
            f"Lookup filtros: ['{name}'] hints={[args.get('search_hint')]} "
            f"col={args.get('column_name')}",
        )
        try:
            result = LOOKUP_BY_NAME[name].invoke(args, config=config)
            content = json.dumps(result, ensure_ascii=False, default=str)
        except Exception as exc:
            content = json.dumps(
                {"error": str(exc), "note": "Corrija argumentos e intente de nuevo."},
                ensure_ascii=False,
            )
        messages.append(
            ToolMessage(content=content, tool_call_id=tc_id, name=name)
        )
    return messages


def _collect_lookup_results(messages: list) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        try:
            payload = json.loads(message_content_to_str(msg.content))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            results.append(payload)
    return results


def _summarize_lookup_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return "No se ejecutaron búsquedas de filtros en el cubo."

    lines = ["RESULTADOS LOOKUP (usa estos valores EXACTOS en el DAX):"]
    for idx, result in enumerate(results, start=1):
        column = result.get("column") or result.get("column_name") or "?"
        table = result.get("table") or result.get("table_name") or "?"
        hint = result.get("search_hint") or ""
        if result.get("error"):
            lines.append(f"  {idx}. {table}[{column}] hint='{hint}': ERROR — {result['error'][:160]}")
            continue
        matches = result.get("matches") or []
        if matches:
            values = ", ".join(str(m.get("value")) for m in matches[:8])
            lines.append(f"  {idx}. {table}[{column}] hint='{hint}': {values}")
        else:
            lines.append(f"  {idx}. {table}[{column}] hint='{hint}': sin coincidencias")

    lines.extend(
        [
            "",
            "Instrucciones:",
            "- Si hay coincidencias, usa el valor exacto en FILTER/TREATAS.",
            "- Si no hay coincidencias para un país, genera DAX igual (TOPN/SUMMARIZECOLUMNS) "
            "con la mejor columna geográfica disponible.",
            "- Para 'regiones en [país]': filtra por Pais_Destino (o Pais Cliente Operación) "
            "y agrupa por Region_Destino con COUNTROWS o DISTINCTCOUNT.",
            "- NO vuelvas a llamar lookup; escribe el DAX ahora.",
        ]
    )
    return "\n".join(lines)


def _build_user_payload(state: AgentState) -> str:
    query = state.get("user_query", "").strip()
    parts = [f"Pregunta del usuario:\n{query}"]

    prev = state.get("dax_execution_result") or {}
    err = execution_error(prev) if prev and not prev.get("ok") else ""
    retries = state.get("dax_retries", 0)
    previous_dax = state.get("generated_dax", "")

    if err:
        dax_hint = previous_dax or "(vacío)"
        if previous_dax and not is_valid_dax_structure(sanitize_dax_query(previous_dax)):
            dax_hint = (
                "(consulta inválida — no repitas instrucciones del prompt; "
                "genera EVALUATE + ROW/FILTER/SUMMARIZECOLUMNS/TOPN con tablas del cubo)"
            )
        parts.append(
            "\nLa ejecución anterior falló. Corrige el DAX.\n"
            f"Reintento actual: {retries}\n"
            f"DAX previo:\n{dax_hint}\n"
            f"Error:\n{compact_execution_error(err)}\n"
            "Genera una consulta DISTINTA (cambia filtros, columnas o agregación). "
            "No repitas el mismo DAX."
        )
    return "\n".join(parts)


def _generate_dax_query(
    *,
    state: AgentState,
    lookup_results: list[dict[str, Any]],
    config: RunnableConfig,
    trace: Any,
) -> tuple[str, str]:
    """Genera DAX con mensajes limpios (sin ToolMessage) para evitar errores 400 del LLM."""
    user_payload = _build_user_payload(state)
    lookup_summary = _summarize_lookup_results(lookup_results)

    final_messages = [
        SystemMessage(content=dax_translator_prompt()),
        HumanMessage(content=f"{user_payload}\n\n{lookup_summary}"),
        HumanMessage(
            content=(
                "FASE FINAL — NO uses herramientas.\n"
                "Devuelve dax_query con SOLO código DAX (empieza con EVALUATE).\n"
                "Funciones válidas: SUMMARIZECOLUMNS, TOPN, FILTER, ROW, COUNTROWS.\n"
                "PROHIBIDO en dax_query: markdown, explicaciones, notas, viñetas, "
                "texto de instrucciones o rationale.\n"
                "Si quieres justificar, usa el campo rationale (aparte)."
            )
        ),
    ]

    structured = get_llm(max_tokens=800).with_structured_output(DaxOutput)
    parsed: DaxOutput = structured.invoke(final_messages, config=config)
    return (parsed.dax_query or "").strip(), (parsed.rationale or "")


def dax_translator_agent(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Genera únicamente generated_dax a partir de user_query (+ error previo)."""
    trace = get_trace(state)
    trace.log("dax_translator", "Generando consulta DAX...")
    t0 = time.perf_counter()

    llm_tools = get_llm(max_tokens=700).bind_tools(LOOKUP_TOOLS)
    messages: list = [
        SystemMessage(content=dax_translator_lookup_prompt()),
        HumanMessage(content=_build_user_payload(state)),
    ]

    # Fase 1: lookups opcionales (máximo 2 rondas, 2 tools por ronda)
    for round_idx in range(MAX_LOOKUP_LOOPS):
        response = llm_tools.invoke(messages, config=config)
        messages.append(response)
        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            break

        if len(tool_calls) > MAX_TOOL_CALLS_PER_ROUND:
            trace.log(
                "dax_translator",
                f"Limitando lookups: {len(tool_calls)} → {MAX_TOOL_CALLS_PER_ROUND}",
                "warn",
            )
            tool_calls = tool_calls[:MAX_TOOL_CALLS_PER_ROUND]

        messages.extend(
            _run_lookup_tool_calls(
                tool_calls,
                user_query=state.get("user_query", ""),
                config=config,
                trace=trace,
            )
        )

        if round_idx + 1 >= MAX_LOOKUP_LOOPS:
            messages.append(
                HumanMessage(
                    content=(
                        "Límite de lookups alcanzado. No llames más herramientas. "
                        "En la siguiente respuesta escribe solo el DAX final."
                    )
                )
            )
            break

        messages.append(
            HumanMessage(
                content=(
                    "Usa los resultados anteriores. Si ya tienes el valor del filtro, "
                    "NO llames más herramientas y responde con el DAX."
                )
            )
        )

    lookup_results = _collect_lookup_results(messages)
    dax_query = ""
    rationale = ""

    try:
        dax_query, rationale = _generate_dax_query(
            state=state,
            lookup_results=lookup_results,
            config=config,
            trace=trace,
        )
    except Exception as exc:
        trace.log("dax_translator", f"Generación DAX falló: {exc}", "warn")
        # Fallback: buscar DAX en la última respuesta del modelo con tools
        for msg in reversed(messages):
            if isinstance(msg, SystemMessage | ToolMessage):
                continue
            content = message_content_to_str(getattr(msg, "content", ""))
            dax_query = extract_dax_from_text(content)
            if dax_query:
                break

    dax_query = sanitize_dax_query(dax_query)
    if dax_query and not is_valid_dax_structure(dax_query):
        trace.log(
            "dax_translator",
            "DAX extraído inválido (texto mezclado / eco del prompt); se descarta.",
            "warn",
        )
        dax_query = ""

    # Preview seguro en log (sin volcar prosa larga)
    preview = dax_query.replace("\n", " ")[:160] if dax_query else "(vacío)"
    elapsed = int((time.perf_counter() - t0) * 1000)
    trace.log(
        "dax_translator",
        f"DAX listo en {elapsed}ms ({len(dax_query)} chars, {len(lookup_results)} lookups) "
        f"— {preview}"
        + (f" | rationale: {rationale[:80]}" if rationale else ""),
    )

    return {
        "generated_dax": dax_query,
        "current_dax_query": dax_query,
        "validation_error": (
            "No se pudo generar una consulta DAX válida."
            if not dax_query
            else ""
        ),
        "_trace": trace,
    }
