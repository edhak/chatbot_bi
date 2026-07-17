"""
Servicio de dashboard: re-ejecuta DAX y regenera gráficos desde el cubo.
"""

from __future__ import annotations

import os
import time
from typing import Any

from agent_api.core.chart_builder import ensure_echarts_config
from agent_api.core.dashboard_store import (
    add_item,
    find_by_dax,
    find_by_id,
    list_items,
    remove_item,
    update_item_meta,
)
from agent_api.core.security import get_allowed_cube_address, truncate_rows, validate_dax_query
from agent_api.tools.ssas_client import SSASConnectionError, execute_dax_query as run_dax


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _execute_dax(cube_address: str, dax_query: str) -> list[dict[str, Any]]:
    safe_query = validate_dax_query(dax_query)
    use_mock = os.getenv("SSAS_USE_MOCK", "false").lower() == "true"

    if use_mock:
        from agent_api.tools.ssas_executor import _execute_mock

        return _execute_mock(safe_query)

    rows = run_dax(cube_address, safe_query)
    return truncate_rows(rows)


def _build_chart_for_item(item: dict[str, Any], cube_address: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        raw_data = _execute_dax(cube_address, item["dax_query"])
        chart_config = ensure_echarts_config(None, raw_data, title=item.get("title", "Indicador BI"))
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        update_item_meta(
            item["id"],
            last_refresh_at=_now_iso(),
            last_error=None,
        )
        return {
            "id": item["id"],
            "title": item["title"],
            "question": item.get("question", ""),
            "dax_query": item["dax_query"],
            "chartConfig": chart_config,
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "last_refresh_at": _now_iso(),
            "last_error": None,
            "elapsed_ms": elapsed_ms,
            "row_count": len(raw_data),
        }
    except (SSASConnectionError, ValueError, RuntimeError) as exc:
        update_item_meta(item["id"], last_error=str(exc))
        return {
            "id": item["id"],
            "title": item["title"],
            "question": item.get("question", ""),
            "dax_query": item["dax_query"],
            "chartConfig": {},
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "last_refresh_at": item.get("last_refresh_at"),
            "last_error": str(exc),
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
            "row_count": 0,
        }


def get_dashboard_entries(cube_address: str | None = None) -> list[dict[str, Any]]:
    cube = get_allowed_cube_address(cube_address)
    return [_build_chart_for_item(item, cube) for item in list_items()]


def create_dashboard_entry(
    *,
    title: str,
    question: str,
    dax_query: str,
    cube_address: str | None = None,
) -> dict[str, Any]:
    validate_dax_query(dax_query)
    item = add_item(title=title, question=question, dax_query=dax_query)
    cube = get_allowed_cube_address(cube_address)
    return _build_chart_for_item(item, cube)


def delete_dashboard_entry(item_id: str) -> bool:
    return remove_item(item_id)


def refresh_dashboard_entry(item_id: str, cube_address: str | None = None) -> dict[str, Any]:
    item = find_by_id(item_id)
    if not item:
        raise ValueError("El indicador no existe en el dashboard.")
    cube = get_allowed_cube_address(cube_address)
    return _build_chart_for_item(item, cube)


def refresh_all_dashboard_entries(cube_address: str | None = None) -> list[dict[str, Any]]:
    return get_dashboard_entries(cube_address)


def is_dax_in_dashboard(dax_query: str) -> dict[str, Any] | None:
    return find_by_dax(dax_query)
