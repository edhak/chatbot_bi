"""
Estado compartido del pipeline multi-agente BI (LangGraph).
"""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict

from agent_api.core.debug_log import AgentDebugTrace


class AgentState(TypedDict):
    """Estado transaccional entre agentes del pipeline."""

    # --- Pipeline (contrato multi-agente) ---
    user_query: str
    generated_dax: str
    dax_execution_result: dict[str, Any]
    dax_retries: int
    data_profile_summary: str
    chart_configuration: dict[str, Any]

    # --- Respuesta al usuario / API ---
    response_text: NotRequired[str]
    response_dax: NotRequired[str]

    # --- Compatibilidad con consumidores existentes ---
    # current_dax_query / raw_data / echarts_config / retry_count se sincronizan
    # en los nodos para no romper dashboard y contratos legacy.
    current_dax_query: NotRequired[str]
    raw_data: NotRequired[list[dict[str, Any]]]
    echarts_config: NotRequired[dict[str, Any]]
    retry_count: NotRequired[int]
    validation_error: NotRequired[str]

    # --- Debug ---
    _trace: NotRequired[AgentDebugTrace]
