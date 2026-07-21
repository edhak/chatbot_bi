"""
Ejecución mock de DAX (desarrollo sin SSAS).
La ejecución real va por execute_dax_node → ssas_client.
"""

from __future__ import annotations

from typing import Any


def _execute_mock(dax_query: str) -> list[dict[str, Any]]:
    """Respuesta mínima para SSAS_USE_MOCK=true."""
    _ = dax_query
    return [{"Total registros": 965}]
