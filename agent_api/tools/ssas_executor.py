"""
Herramienta LangChain para ejecutar consultas DAX contra SSAS Tabular.
"""

from __future__ import annotations

import os
from typing import Annotated, Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg, tool

from agent_api.core.security import truncate_rows, validate_dax_query
from agent_api.tools.ssas_client import SSASConnectionError, execute_dax_query as run_dax


@tool
def execute_dax_query(
    dax_query: str,
    config: Annotated[RunnableConfig, InjectedToolArg],
) -> list[dict[str, Any]]:
    """
    Ejecuta una consulta DAX de solo lectura (EVALUATE ...) contra el cubo SSAS.

    Args:
        dax_query: Consulta DAX válida que comienza con EVALUATE.

    Returns:
        Lista de registros (máximo 200 filas).
    """
    safe_query = validate_dax_query(dax_query)
    cube_address = config["configurable"].get("cube_address", "")
    use_mock = os.getenv("SSAS_USE_MOCK", "false").lower() == "true"

    print(f"[SSAS] Ejecutando DAX ({len(safe_query)} chars), mock={use_mock}")

    if use_mock:
        rows = _execute_mock(safe_query)
        print(f"[SSAS] Mock devolvió {len(rows)} filas")
        return rows

    try:
        rows = run_dax(cube_address, safe_query)
        truncated = truncate_rows(rows)
        print(f"[SSAS] Cubo devolvió {len(rows)} filas (enviando {len(truncated)})")
        return truncated
    except SSASConnectionError as exc:
        raise RuntimeError(str(exc)) from exc


def _execute_mock(dax_query: str) -> list[dict[str, Any]]:
    return [{"Total registros": 965}]
