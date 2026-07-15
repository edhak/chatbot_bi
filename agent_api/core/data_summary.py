"""
Resumen de datos para reducir tokens enviados al LLM.
"""

from __future__ import annotations

import json
from typing import Any


def summarize_rows_for_llm(rows: list[dict[str, Any]], max_rows: int = 12) -> str:
    """Compacta resultados DAX para el contexto del modelo."""
    if not rows:
        return "Sin filas."

    total = len(rows)
    sample = rows[:max_rows]
    payload = {
        "total_filas": total,
        "muestra": sample,
    }
    if total > max_rows:
        payload["nota"] = f"Mostrando {max_rows} de {total} filas."

    return json.dumps(payload, ensure_ascii=False, default=str)
