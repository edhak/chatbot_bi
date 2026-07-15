"""
Estado compartido del grafo LangGraph para el agente analítico.
"""

from __future__ import annotations

from typing import Annotated, Any, NotRequired, TypedDict

from langgraph.graph.message import add_messages

from agent_api.core.debug_log import AgentDebugTrace


class AgentState(TypedDict):
    """Estado del flujo ReAct del agente BI."""

    messages: Annotated[list, add_messages]
    current_dax_query: str
    raw_data: list[dict[str, Any]]
    echarts_config: dict[str, Any]
    retry_count: int
    validation_error: NotRequired[str]
    response_text: NotRequired[str]
    response_dax: NotRequired[str]
    _trace: NotRequired[AgentDebugTrace]
