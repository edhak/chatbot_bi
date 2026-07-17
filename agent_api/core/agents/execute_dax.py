"""
Nodo ejecutor: corre generated_dax contra SSAS (o mock).
"""

from __future__ import annotations

import os
import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from agent_api.core.agents.llm_utils import get_trace
from agent_api.core.security import truncate_rows, validate_dax_query
from agent_api.core.state import AgentState
from agent_api.tools.ssas_client import SSASConnectionError, execute_dax_query as run_dax
from agent_api.tools.ssas_executor import _execute_mock


def execute_dax_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """
    Ejecuta el DAX del estado.
    Éxito → dax_execution_result.ok=True + rows.
    Error / 0 filas → ok=False + error, incrementa dax_retries.
    """
    from agent_api.core.agents.llm_utils import is_valid_dax_structure, sanitize_dax_query

    trace = get_trace(state)
    dax = sanitize_dax_query(state.get("generated_dax") or "")
    if dax and not is_valid_dax_structure(dax):
        dax = ""
    retries = int(state.get("dax_retries", 0))
    cube_address = ""
    if config and isinstance(config, dict):
        cube_address = (config.get("configurable") or {}).get("cube_address", "")

    if not dax:
        retries += 1
        result = {
            "ok": False,
            "error": (
                "No se generó una consulta DAX válida (vacía o con texto mezclado). "
                "Genere SOLO EVALUATE + expresión DAX, sin instrucciones ni prosa."
            ),
            "rows": [],
        }
        trace.log("execute_dax", result["error"], "error")
        return {
            "dax_execution_result": result,
            "dax_retries": retries,
            "retry_count": retries,
            "raw_data": [],
            "generated_dax": "",
            "current_dax_query": "",
            "validation_error": result["error"],
            "_trace": trace,
        }

    # Evitar re-ejecutar el mismo DAX que ya falló en este pipeline
    prev = state.get("dax_execution_result") or {}
    prev_dax = str(prev.get("dax_query") or "").strip()
    if prev_dax and prev_dax == dax and not prev.get("ok"):
        retries += 1
        error = (
            "Se regeneró la misma consulta DAX que ya falló. "
            "Debe cambiar filtros, columnas, agregación o sintaxis."
        )
        result = {"ok": False, "error": error, "rows": [], "dax_query": dax}
        trace.log("execute_dax", f"DAX duplicado — retry={retries}", "warn")
        return {
            "dax_execution_result": result,
            "dax_retries": retries,
            "retry_count": retries,
            "raw_data": [],
            "current_dax_query": dax,
            "validation_error": error,
            "_trace": trace,
        }

    trace.log("execute_dax", f"Ejecutando DAX ({len(dax)} chars)...")
    t0 = time.perf_counter()

    try:
        safe_query = validate_dax_query(dax)
        use_mock = os.getenv("SSAS_USE_MOCK", "false").lower() == "true"

        if use_mock:
            rows = _execute_mock(safe_query)
        else:
            rows = truncate_rows(run_dax(cube_address, safe_query))

        elapsed = int((time.perf_counter() - t0) * 1000)

        if not rows:
            retries += 1
            error = (
                "La consulta DAX no devolvió filas. "
                "Revise filtros (use valores exactos del cubo vía lookup) "
                "o tablas/columnas del diccionario."
            )
            result = {"ok": False, "error": error, "rows": [], "dax_query": safe_query}
            trace.log("execute_dax", f"0 filas en {elapsed}ms — retry={retries}", "warn")
            return {
                "dax_execution_result": result,
                "dax_retries": retries,
                "retry_count": retries,
                "raw_data": [],
                "current_dax_query": safe_query,
                "validation_error": error,
                "_trace": trace,
            }

        result = {"ok": True, "rows": rows, "dax_query": safe_query, "row_count": len(rows)}
        trace.log("execute_dax", f"OK — {len(rows)} filas en {elapsed}ms")
        # Coerce tipos .NET para que profiler/viz detecten medidas
        try:
            from agent_api.core.chart_selector import coerce_rows_for_charts

            rows = coerce_rows_for_charts(rows)
            result["rows"] = rows
        except Exception:
            pass
        return {
            "dax_execution_result": result,
            "raw_data": rows,
            "current_dax_query": safe_query,
            "validation_error": "",
            "_trace": trace,
        }

    except (ValueError, SSASConnectionError, RuntimeError, Exception) as exc:
        retries += 1
        elapsed = int((time.perf_counter() - t0) * 1000)
        error = str(exc)
        result = {"ok": False, "error": error, "rows": [], "dax_query": dax}
        trace.log("execute_dax", f"Error en {elapsed}ms: {error[:180]}", "error")
        return {
            "dax_execution_result": result,
            "dax_retries": retries,
            "retry_count": retries,
            "raw_data": [],
            "current_dax_query": dax,
            "validation_error": error,
            "_trace": trace,
        }
