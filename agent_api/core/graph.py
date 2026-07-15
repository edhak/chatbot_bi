"""
Grafo LangGraph ReAct para el agente analítico BI.
"""

from __future__ import annotations

import json
import os
import re
import time
from functools import lru_cache
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from agent_api.core.chart_builder import ensure_echarts_config
from agent_api.core.data_summary import summarize_rows_for_llm
from agent_api.core.debug_log import AgentDebugTrace, is_debug_enabled
from agent_api.core.state import AgentState
from agent_api.metadata.cube_dictionary import get_cube_dictionary_prompt
from agent_api.tools.ssas_executor import execute_dax_query

TOOLS = [execute_dax_query]
TOOL_NODE = ToolNode(TOOLS)

MAX_DAX_RETRIES = 1

_LLM_TOOLS: ChatOpenAI | None = None
_LLM_FINAL: ChatOpenAI | None = None


class FinalizeOutput(BaseModel):
    """Respuesta estructurada del nodo finalize."""

    text_response: str = Field(description="Narrativa ejecutiva breve; Markdown permitido.")
    dax_query: str = Field(description="Consulta DAX utilizada en el análisis.")


@lru_cache(maxsize=1)
def _build_system_prompt() -> str:
    cube_dict = get_cube_dictionary_prompt()
    return f"""Eres un experto analista BI para cubos Tabular SSAS.
{cube_dict}

Tu tarea: generar UNA consulta DAX y llamar a execute_dax_query.
- DAX debe comenzar con EVALUATE.
- Usa solo tablas/columnas del diccionario.
- Llama a la herramienta una sola vez.
- No escribas la respuesta final todavía; solo ejecuta la consulta.
"""


@lru_cache(maxsize=1)
def _build_finalize_prompt() -> str:
    return """Genera la respuesta ejecutiva para gerencia usando los datos del cubo.

Reglas:
- Máximo 3 párrafos o una lista corta.
- No inventes cifras; usa solo los datos de la herramienta.
- La consulta DAX va solo en el campo dax_query; no la repitas en text_response.
"""


def _llm_tools() -> ChatOpenAI:
    global _LLM_TOOLS
    if _LLM_TOOLS is None:
        _LLM_TOOLS = ChatOpenAI(
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            temperature=0.1,
            timeout=int(os.getenv("LLM_TIMEOUT_SEC", "60")),
            max_tokens=800,
        ).bind_tools(TOOLS)
    return _LLM_TOOLS


def _llm_final() -> ChatOpenAI:
    global _LLM_FINAL
    if _LLM_FINAL is None:
        _LLM_FINAL = ChatOpenAI(
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            temperature=0.1,
            timeout=int(os.getenv("LLM_TIMEOUT_SEC", "60")),
            max_tokens=1200,
        )
    return _LLM_FINAL


def _message_content_to_str(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text") or block.get("content") or block))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content)


def _extract_json_from_text(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                return None
    return None


def _compress_tool_messages(messages: list) -> list:
    compressed = []
    for msg in messages:
        if isinstance(msg, ToolMessage) and msg.name == "execute_dax_query":
            content = msg.content
            rows: list[dict[str, Any]] = []
            if isinstance(content, list):
                rows = content
            elif isinstance(content, str):
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, list):
                        rows = parsed
                except json.JSONDecodeError:
                    pass
            summary = summarize_rows_for_llm(rows) if rows else str(content)
            compressed.append(
                ToolMessage(content=summary, tool_call_id=msg.tool_call_id, name=msg.name)
            )
        else:
            compressed.append(msg)
    return compressed


def _looks_like_dax(text: str) -> bool:
    """Detecta si un texto parece consulta DAX y no debe usarse como título del gráfico."""
    stripped = text.strip()
    if not stripped:
        return True
    upper = stripped.upper()
    if upper.startswith("EVALUATE") or upper.startswith("DEFINE"):
        return True
    dax_markers = (
        "SUMMARIZECOLUMNS",
        "COUNTROWS(",
        "TOPN(",
        "ROW(",
        "ORDER BY",
        "VAR ",
        "'BI_FLOTHS",
        "MOD01_EQUIPO",
    )
    return any(marker in upper for marker in dax_markers)


def _sanitize_chart_title_line(text: str) -> str:
    line = re.sub(r"^\*\*|\*\*$", "", text.strip()).strip()
    line = re.sub(r"^#+\s*", "", line).strip()
    if not line or _looks_like_dax(line):
        return ""
    if line.startswith("```"):
        return ""
    return line[:80]


def _chart_title_from_parsed(
    parsed: dict[str, Any] | None,
    question: str = "",
) -> str:
    candidates: list[str] = []

    if parsed and parsed.get("text_response"):
        for line in str(parsed["text_response"]).split("\n"):
            cleaned = _sanitize_chart_title_line(line)
            if cleaned:
                candidates.append(cleaned)

    if question.strip():
        q = _sanitize_chart_title_line(question.strip())
        if q and q not in candidates:
            candidates.append(q)

    if candidates:
        return candidates[0]
    return "Resultado de la consulta"


def _build_agent_response(
    *,
    text_response: str,
    dax_query: str,
    raw_data: list[dict[str, Any]],
    parsed: dict[str, Any] | None = None,
    question: str = "",
    trace: AgentDebugTrace,
) -> dict[str, Any]:
    chart_config = ensure_echarts_config(
        None,
        raw_data,
        title=_chart_title_from_parsed(parsed, question=question),
    )
    has_chart = bool(chart_config.get("series"))
    trace.log(
        "build_response",
        f"text_len={len(text_response)} dax_len={len(dax_query)} "
        f"raw_rows={len(raw_data)} has_chart={has_chart}",
    )

    return {
        "text_response": text_response or "(Sin texto de respuesta del agente)",
        "dax_query": dax_query,
        "echarts_config": chart_config,
        "raw_data": raw_data,
        "debug_log": trace.to_list() if is_debug_enabled() else [],
    }


def _get_trace(state: AgentState) -> AgentDebugTrace:
    trace = state.get("_trace")
    if trace is None:
        trace = AgentDebugTrace()
    return trace


def call_model(state: AgentState) -> dict[str, Any]:
    trace = _get_trace(state)
    trace.log("agent", "Invocando LLM para generar DAX...")
    t0 = time.perf_counter()

    llm = _llm_tools()
    system_msg = SystemMessage(content=_build_system_prompt())
    messages = [system_msg, *state["messages"]]
    response = llm.invoke(messages)

    elapsed = int((time.perf_counter() - t0) * 1000)
    tool_calls = getattr(response, "tool_calls", None) or []
    trace.log("agent", f"LLM respondió en {elapsed}ms, tool_calls={len(tool_calls)}")
    return {"messages": [response], "_trace": trace}


def finalize_response(state: AgentState) -> dict[str, Any]:
    trace = _get_trace(state)
    trace.log("finalize", "Generando respuesta narrativa (structured output)...")
    t0 = time.perf_counter()

    llm = _llm_final().with_structured_output(FinalizeOutput)
    system_msg = SystemMessage(content=_build_finalize_prompt())
    history = _compress_tool_messages(state["messages"])
    messages = [system_msg, *history]

    parsed: FinalizeOutput | None = None
    try:
        parsed = llm.invoke(messages)
    except Exception as exc:
        trace.log("finalize", f"Structured output falló: {exc}", "warn")
        fallback = _llm_final().invoke(messages)
        content = _message_content_to_str(fallback.content)
        raw = _extract_json_from_text(content)
        if raw:
            parsed = FinalizeOutput(
                text_response=str(raw.get("text_response") or content),
                dax_query=str(raw.get("dax_query") or state.get("current_dax_query", "")),
            )
        else:
            parsed = FinalizeOutput(
                text_response=content or "No se pudo generar narrativa.",
                dax_query=state.get("current_dax_query", ""),
            )

    elapsed = int((time.perf_counter() - t0) * 1000)
    trace.log("finalize", f"Respuesta final en {elapsed}ms, chars={len(parsed.text_response)}")
    return {
        "messages": [AIMessage(content=parsed.model_dump_json())],
        "response_text": parsed.text_response,
        "response_dax": parsed.dax_query or state.get("current_dax_query", ""),
        "_trace": trace,
    }


def no_tool_response(state: AgentState) -> dict[str, Any]:
    trace = _get_trace(state)
    last_message = state["messages"][-1]
    content = ""
    if isinstance(last_message, AIMessage):
        content = _message_content_to_str(last_message.content).strip()

    text = content or (
        "No pude generar una consulta DAX para su pregunta. "
        "Intente reformularla indicando métricas, dimensiones o filtros del cubo."
    )
    trace.log("no_tool_response", "Agente finalizó sin invocar execute_dax_query", "warn")
    return {"response_text": text, "response_dax": "", "_trace": trace}


def _tool_message_indicates_error(content: Any) -> str | None:
    if isinstance(content, str):
        lowered = content.lower()
        if any(token in lowered for token in ("error", "exception", "falló", "failed")):
            return content
        return None
    return None


def validate_results(state: AgentState) -> dict[str, Any]:
    trace = _get_trace(state)
    raw_data = state.get("raw_data", [])
    validation_error = ""

    for msg in reversed(state["messages"]):
        if isinstance(msg, ToolMessage) and msg.name == "execute_dax_query":
            tool_error = _tool_message_indicates_error(msg.content)
            if tool_error:
                validation_error = tool_error
            elif not raw_data:
                validation_error = (
                    "La consulta DAX no devolvió filas. "
                    "Revise filtros, tablas o columnas del diccionario."
                )
            break

    if validation_error:
        trace.log("validate_results", validation_error[:200], "warn")
    else:
        trace.log("validate_results", f"OK — {len(raw_data)} filas")

    return {"validation_error": validation_error, "_trace": trace}


def retry_agent(state: AgentState) -> dict[str, Any]:
    trace = _get_trace(state)
    err = state.get("validation_error", "Sin datos")
    dax = state.get("current_dax_query", "")
    retry_count = state.get("retry_count", 0) + 1
    trace.log("retry_agent", f"Reintento {retry_count}/{MAX_DAX_RETRIES}")

    hint = HumanMessage(
        content=(
            "La consulta DAX anterior falló o no devolvió datos útiles.\n"
            f"DAX previo: {dax or '(vacío)'}\n"
            f"Detalle: {err}\n"
            "Genera una consulta DAX distinta y vuelve a llamar execute_dax_query."
        ),
    )
    return {
        "messages": [hint],
        "retry_count": retry_count,
        "validation_error": "",
        "raw_data": [],
        "current_dax_query": "",
        "_trace": trace,
    }


def error_response(state: AgentState) -> dict[str, Any]:
    trace = _get_trace(state)
    err = state.get("validation_error", "No se obtuvieron datos del cubo.")
    dax = state.get("current_dax_query", "")
    text = (
        "No fue posible obtener datos tras reintentar la consulta.\n\n"
        f"**Detalle:** {err}\n\n"
        "Sugerencia: reformule la pregunta o acote filtros (año, región, tipo de equipo)."
    )
    trace.log("error_response", "Respuesta de error al usuario", "error")
    return {"response_text": text, "response_dax": dax, "_trace": trace}


def _route_after_model(state: AgentState) -> Literal["tools", "no_tool"]:
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    return "no_tool"


def _route_after_validate(state: AgentState) -> Literal["finalize", "retry_agent", "error_response"]:
    if not state.get("validation_error"):
        return "finalize"
    if state.get("retry_count", 0) < MAX_DAX_RETRIES:
        return "retry_agent"
    return "error_response"


def _process_tool_results(state: AgentState) -> dict[str, Any]:
    trace = _get_trace(state)
    raw_data: list[dict[str, Any]] = []
    dax_query = ""

    for msg in reversed(state["messages"]):
        if isinstance(msg, ToolMessage) and msg.name == "execute_dax_query":
            content = msg.content
            if isinstance(content, list):
                raw_data = content
            elif isinstance(content, str):
                tool_error = _tool_message_indicates_error(content)
                if tool_error:
                    raw_data = []
                else:
                    try:
                        parsed = json.loads(content)
                        raw_data = parsed if isinstance(parsed, list) else []
                    except json.JSONDecodeError:
                        trace.log("process_results", f"Tool devolvió texto: {content[:200]}", "warn")
                        raw_data = []
            break

    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc["name"] == "execute_dax_query":
                    dax_query = tc["args"].get("dax_query", "")
                    break
            if dax_query:
                break

    trace.log(
        "process_results",
        f"DAX ejecutado, filas={len(raw_data)}, query={dax_query[:120]}...",
    )
    return {"raw_data": raw_data, "current_dax_query": dax_query, "_trace": trace}


def _run_tools(state: AgentState) -> dict[str, Any]:
    trace = _get_trace(state)
    trace.log("tools", "Ejecutando herramienta execute_dax_query...")
    t0 = time.perf_counter()
    result = TOOL_NODE.invoke(state)
    elapsed = int((time.perf_counter() - t0) * 1000)
    trace.log("tools", f"Herramienta completada en {elapsed}ms")
    result["_trace"] = trace
    return result


def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("agent", call_model)
    workflow.add_node("tools", _run_tools)
    workflow.add_node("process_results", _process_tool_results)
    workflow.add_node("validate_results", validate_results)
    workflow.add_node("retry_agent", retry_agent)
    workflow.add_node("finalize", finalize_response)
    workflow.add_node("no_tool_response", no_tool_response)
    workflow.add_node("error_response", error_response)

    workflow.set_entry_point("agent")
    workflow.add_conditional_edges(
        "agent",
        _route_after_model,
        {"tools": "tools", "no_tool": "no_tool_response"},
    )
    workflow.add_edge("tools", "process_results")
    workflow.add_edge("process_results", "validate_results")
    workflow.add_conditional_edges(
        "validate_results",
        _route_after_validate,
        {
            "finalize": "finalize",
            "retry_agent": "retry_agent",
            "error_response": "error_response",
        },
    )
    workflow.add_edge("retry_agent", "agent")
    workflow.add_edge("no_tool_response", END)
    workflow.add_edge("error_response", END)
    workflow.add_edge("finalize", END)

    return workflow.compile()


agent_graph = build_graph()


def _resolve_response_from_state(
    result: AgentState,
    trace: AgentDebugTrace,
    question: str = "",
) -> dict[str, Any] | None:
    response_text = result.get("response_text")
    if not response_text:
        return None

    dax_query = result.get("response_dax") or result.get("current_dax_query", "")
    raw_data = result.get("raw_data", [])
    parsed = {"text_response": response_text, "dax_query": dax_query}
    trace.log("parse", "Respuesta tomada del estado del grafo")
    return _build_agent_response(
        text_response=response_text,
        dax_query=dax_query,
        raw_data=raw_data,
        parsed=parsed,
        question=question,
        trace=trace,
    )


def run_agent(question: str, cube_address: str) -> dict[str, Any]:
    trace = AgentDebugTrace()
    trace.log("start", f"Pregunta recibida: {question[:100]}")

    initial_state: AgentState = {
        "messages": [HumanMessage(content=question)],
        "current_dax_query": "",
        "raw_data": [],
        "echarts_config": {},
        "retry_count": 0,
        "_trace": trace,
    }

    config = {
        "configurable": {"cube_address": cube_address},
        "recursion_limit": int(os.getenv("AGENT_RECURSION_LIMIT", "10")),
    }

    try:
        trace.log("graph", "Ejecutando grafo LangGraph...")
        t0 = time.perf_counter()
        result = agent_graph.invoke(initial_state, config=config)
        trace = result.get("_trace", trace)
        trace.log("graph", f"Grafo completado en {int((time.perf_counter() - t0) * 1000)}ms")
    except Exception as exc:
        trace.log("graph", f"Error en grafo: {exc}", "error")
        return _build_agent_response(
            text_response=f"Error interno del agente: {exc}",
            dax_query="",
            raw_data=[],
            question=question,
            trace=trace,
        )

    early = _resolve_response_from_state(result, trace, question=question)
    if early:
        return early

    raw_data: list[dict[str, Any]] = result.get("raw_data", [])

    last_ai = next(
        (m for m in reversed(result["messages"]) if isinstance(m, AIMessage)),
        None,
    )

    if last_ai:
        content = _message_content_to_str(last_ai.content)
        trace.log("parse", f"Contenido AI crudo: {len(content)} chars")
        if content:
            parsed = _extract_json_from_text(content)
            if parsed:
                trace.log("parse", "JSON extraído correctamente (fallback)")
                return _build_agent_response(
                    text_response=str(parsed.get("text_response") or content),
                    dax_query=str(parsed.get("dax_query") or result.get("current_dax_query", "")),
                    raw_data=raw_data,
                    parsed=parsed,
                    question=question,
                    trace=trace,
                )
            trace.log("parse", "No se pudo parsear JSON, usando texto crudo", "warn")
            return _build_agent_response(
                text_response=content,
                dax_query=result.get("current_dax_query", ""),
                raw_data=raw_data,
                question=question,
                trace=trace,
            )

    trace.log("parse", "Sin respuesta del modelo", "error")
    return _build_agent_response(
        text_response="No se pudo generar una respuesta.",
        dax_query=result.get("current_dax_query", ""),
        raw_data=raw_data,
        question=question,
        trace=trace,
    )
