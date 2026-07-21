"""
Servicio de dashboard: re-ejecuta DAX y regenera gráficos desde el cubo.
Cada indicador conserva su fuente original (cube_address + seudonimo).
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
    update_item_source,
)
from agent_api.core.data_sources import get_data_source, list_data_sources
from agent_api.core.security import get_allowed_cube_address, truncate_rows, validate_dax_query
from agent_api.metadata.cube_dictionary import load_cube_schema
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


def _infer_source_from_dax(dax_query: str) -> dict[str, Any] | None:
    """
    Infiere seudónimo/cubo comparando tablas del DAX con los diccionarios de cada fuente.
    """
    dax_l = (dax_query or "").lower()
    if not dax_l.strip():
        return None

    best: dict[str, Any] | None = None
    best_hits = 0
    for src in list_data_sources():
        rel = str(src.get("ruta_diccionario") or "").strip()
        if not rel:
            continue
        try:
            schema = load_cube_schema(rel)
        except Exception:
            continue
        hits = 0
        for table in schema.tables:
            name = (table.name or "").strip()
            if name and name.lower() in dax_l:
                hits += 1
            for alias in table.aliases or []:
                if alias and alias.lower() in dax_l:
                    hits += 1
                    break
        if hits > best_hits:
            best_hits = hits
            best = src
    return best if best_hits > 0 else None


def _resolve_item_cube(
    item: dict[str, Any],
    fallback: str | None = None,
    *,
    persist: bool = True,
) -> str:
    """
    Cubo a usar para este indicador (prioridad):
      1) cube_address guardado en el ítem
      2) ruta_cubo del seudónimo guardado
      3) inferencia desde tablas del DAX vs diccionarios
      4) fallback de la petición / DEFAULT (último recurso)
    """
    stored = (item.get("cube_address") or "").strip()
    seudonimo = (item.get("seudonimo") or "").strip() or None

    if not stored and seudonimo:
        src = get_data_source(seudonimo)
        if src and src.get("ruta_cubo"):
            stored = str(src["ruta_cubo"]).strip()

    if not stored:
        inferred = _infer_source_from_dax(str(item.get("dax_query") or ""))
        if inferred:
            seudonimo = seudonimo or str(inferred.get("seudonimo") or "").strip() or None
            if inferred.get("ruta_cubo"):
                stored = str(inferred["ruta_cubo"]).strip()

    if stored:
        cube = get_allowed_cube_address(stored)
        if persist and (
            not (item.get("cube_address") or "").strip()
            or (seudonimo and not (item.get("seudonimo") or "").strip())
        ):
            update_item_source(
                item["id"],
                cube_address=cube,
                seudonimo=seudonimo,
            )
            item["cube_address"] = cube
            if seudonimo:
                item["seudonimo"] = seudonimo
        return cube

    return get_allowed_cube_address(fallback)


def _entry_payload(item: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "id": item["id"],
        "title": item["title"],
        "question": item.get("question", ""),
        "dax_query": item["dax_query"],
        "cube_address": item.get("cube_address"),
        "seudonimo": item.get("seudonimo"),
        "chartConfig": {},
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "last_refresh_at": item.get("last_refresh_at"),
        "last_error": item.get("last_error"),
        "elapsed_ms": 0,
        "row_count": 0,
        **extra,
    }


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
        return _entry_payload(
            item,
            cube_address=item.get("cube_address") or cube_address,
            chartConfig=chart_config,
            last_refresh_at=_now_iso(),
            last_error=None,
            elapsed_ms=elapsed_ms,
            row_count=len(raw_data),
        )
    except (SSASConnectionError, ValueError, RuntimeError) as exc:
        update_item_meta(item["id"], last_error=str(exc))
        return _entry_payload(
            item,
            cube_address=item.get("cube_address") or cube_address,
            chartConfig={},
            last_error=str(exc),
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
            row_count=0,
        )


def get_dashboard_entries(cube_address: str | None = None) -> list[dict[str, Any]]:
    """Carga todos los indicadores; cada uno usa SU cubo original."""
    result: list[dict[str, Any]] = []
    for item in list_items():
        cube = _resolve_item_cube(item, cube_address, persist=True)
        result.append(_build_chart_for_item(item, cube))
    return result


def create_dashboard_entry(
    *,
    title: str,
    question: str,
    dax_query: str,
    cube_address: str | None = None,
    seudonimo: str | None = None,
) -> dict[str, Any]:
    validate_dax_query(dax_query)

    resolved_seudonimo = (seudonimo or "").strip() or None
    cube_from_client = (cube_address or "").strip() or None

    if not cube_from_client and resolved_seudonimo:
        src = get_data_source(resolved_seudonimo)
        if src and src.get("ruta_cubo"):
            cube_from_client = str(src["ruta_cubo"]).strip()

    if not cube_from_client:
        inferred = _infer_source_from_dax(dax_query)
        if inferred:
            resolved_seudonimo = resolved_seudonimo or str(inferred.get("seudonimo") or "").strip() or None
            if inferred.get("ruta_cubo"):
                cube_from_client = str(inferred["ruta_cubo"]).strip()

    cube = get_allowed_cube_address(cube_from_client)
    item = add_item(
        title=title,
        question=question,
        dax_query=dax_query,
        cube_address=cube,
        seudonimo=resolved_seudonimo,
    )
    # Si ya existía sin fuente, completar metadatos
    if not (item.get("cube_address") or "").strip() or (
        resolved_seudonimo and not (item.get("seudonimo") or "").strip()
    ):
        update_item_source(item["id"], cube_address=cube, seudonimo=resolved_seudonimo)
        item["cube_address"] = cube
        if resolved_seudonimo:
            item["seudonimo"] = resolved_seudonimo

    cube_for_item = _resolve_item_cube(item, cube, persist=True)
    return _build_chart_for_item(item, cube_for_item)


def delete_dashboard_entry(item_id: str) -> bool:
    return remove_item(item_id)


def refresh_dashboard_entry(item_id: str, cube_address: str | None = None) -> dict[str, Any]:
    item = find_by_id(item_id)
    if not item:
        raise ValueError("El indicador no existe en el dashboard.")
    # Preferir siempre la fuente del ítem; el cube_address de la query es solo fallback
    cube = _resolve_item_cube(item, cube_address, persist=True)
    return _build_chart_for_item(item, cube)


def refresh_all_dashboard_entries(cube_address: str | None = None) -> list[dict[str, Any]]:
    return get_dashboard_entries(cube_address)


def is_dax_in_dashboard(dax_query: str) -> dict[str, Any] | None:
    return find_by_dax(dax_query)
