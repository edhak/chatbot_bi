"""
Búsqueda de valores de dimensión en el cubo para filtros precisos.
Resuelve diferencias de mayúsculas, tildes y formato (ej. "Perú" vs "PERU").
"""

from __future__ import annotations

import os
import re
import unicodedata
from typing import Annotated, Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg, tool

from agent_api.metadata.cube_dictionary import load_cube_schema, quote_dax_column, quote_dax_table
from agent_api.tools.ssas_client import SSASConnectionError, execute_dax_query as run_dax

_MAX_DISTINCT_VALUES = 300
_MAX_MATCHES = 15

# Mock para desarrollo sin SSAS
_MOCK_DIMENSION_VALUES: dict[tuple[str, str], list[str]] = {
    ("BI_FlotHs Mod01_Equipo", "Pais_Destino"): [
        "PERU",
        "CHILE",
        "COLOMBIA",
        "ECUADOR",
        "BOLIVIA",
        "ARGENTINA",
        "USA",
        "UNITED STATES",
        "ESTADOS UNIDOS",
    ],
    ("BI_FlotHs Mod01_Equipo", "Pais Cliente Operación"): [
        "PERU",
        "CHILE",
        "COLOMBIA",
    ],
    ("BI_FlotHs Mod01_Equipo", "Region_Destino"): [
        "LIMA",
        "AREQUIPA",
        "CUSCO",
        "ANTOFAGASTA",
        "CALIFORNIA",
        "TEXAS",
        "FLORIDA",
        "NEW YORK",
    ],
}


def normalize_match_key(text: str) -> str:
    """Normaliza texto para comparación insensible a tildes y mayúsculas."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFD", str(text).strip())
    without_accents = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    collapsed = re.sub(r"\s+", " ", without_accents)
    return collapsed.upper()


def _resolve_table_column(
    table_name: str,
    column_name: str,
    dictionary_rel: str = "",
) -> tuple[str, str]:
    schema = load_cube_schema(dictionary_rel or "")
    table_key = table_name.strip().lower()
    column_key = column_name.strip().lower()

    def _table_matches(table: Any) -> bool:
        if table.name.lower() == table_key:
            return True
        return any(a.lower() == table_key for a in (table.aliases or []))

    for table in schema.tables:
        if not _table_matches(table):
            continue
        for col in table.columns:
            if col.name.lower() == column_key:
                # Siempre devolver el nombre DAX del cubo (CUBE_TABLE_NAME)
                return table.name, col.name
        raise ValueError(
            f"Columna '{column_name}' no documentada en tabla '{table.name}'. "
            f"Columnas disponibles: {', '.join(c.name for c in table.columns)}"
        )

    known_tables = ", ".join(t.name for t in schema.tables)
    raise ValueError(f"Tabla '{table_name}' no documentada. Tablas DAX: {known_tables}")


def _build_distinct_values_dax(table_name: str, column_name: str) -> str:
    table_ref = quote_dax_table(table_name)
    column_ref = quote_dax_column(table_name, column_name)
    return (
        f"EVALUATE\n"
        f"TOPN({_MAX_DISTINCT_VALUES}, "
        f"FILTER(VALUES({column_ref}), NOT ISBLANK({column_ref})), "
        f"{column_ref}, 1)"
    )


def _score_match(hint_key: str, value: str) -> float:
    value_key = normalize_match_key(value)
    if not hint_key or not value_key:
        return 0.0
    if hint_key == value_key:
        return 1.0
    if hint_key in value_key or value_key in hint_key:
        return 0.85
    # Coincidencia por tokens (ej. "indices peru" -> "PERU")
    hint_tokens = {t for t in re.split(r"[\s,;]+", hint_key) if len(t) >= 3}
    value_tokens = {t for t in re.split(r"[\s,;]+", value_key) if len(t) >= 3}
    if hint_tokens & value_tokens:
        return 0.75
    return 0.0


# Alias comunes → variantes a probar contra valores del cubo
_HINT_ALIASES: dict[str, list[str]] = {
    "ESTADOS UNIDOS": ["USA", "UNITED STATES", "US", "EEUU", "EE.UU.", "U.S.A.", "AMERICA"],
    "EEUU": ["USA", "UNITED STATES", "ESTADOS UNIDOS"],
    "USA": ["UNITED STATES", "ESTADOS UNIDOS", "US"],
    "PERU": ["PERÚ", "PERU"],
    "PERÚ": ["PERU"],
    "CHILE": ["CHILE"],
    "COLOMBIA": ["COLOMBIA"],
    "MEXICO": ["MÉXICO", "MEXICO"],
    "MÉXICO": ["MEXICO"],
}


def _hint_variants(search_hint: str) -> list[str]:
    """Genera variantes del hint para mejorar coincidencias (países, abreviaturas)."""
    base = str(search_hint or "").strip()
    if not base:
        return []

    variants: list[str] = [base]
    key = normalize_match_key(base)

    for label, aliases in _HINT_ALIASES.items():
        label_key = normalize_match_key(label)
        if label_key in key or key in label_key or key in {normalize_match_key(a) for a in aliases}:
            variants.append(label)
            variants.extend(aliases)

    # Dedupe preservando orden
    seen: set[str] = set()
    unique: list[str] = []
    for item in variants:
        norm = normalize_match_key(item)
        if norm and norm not in seen:
            seen.add(norm)
            unique.append(item)
    return unique


def _find_matches_single(hint_key: str, values: list[str]) -> list[dict[str, Any]]:
    if not hint_key:
        return []

    scored: list[tuple[float, str]] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        score = _score_match(hint_key, text)
        if score > 0:
            scored.append((score, text))

    scored.sort(key=lambda item: (-item[0], item[1]))
    seen: set[str] = set()
    matches: list[dict[str, Any]] = []
    for score, text in scored:
        norm = normalize_match_key(text)
        if norm in seen:
            continue
        seen.add(norm)
        matches.append({"value": text, "score": round(score, 2)})
        if len(matches) >= _MAX_MATCHES:
            break
    return matches


def _find_matches(search_hint: str, values: list[str]) -> list[dict[str, Any]]:
    """Busca coincidencias probando variantes del hint (sinónimos de países)."""
    all_scored: dict[str, tuple[float, str]] = {}
    for variant in _hint_variants(search_hint):
        hint_key = normalize_match_key(variant)
        for item in _find_matches_single(hint_key, values):
            value = str(item["value"])
            score = float(item["score"])
            prev = all_scored.get(value)
            if prev is None or score > prev[0]:
                all_scored[value] = (score, value)

    ranked = sorted(all_scored.items(), key=lambda x: (-x[1][0], x[0]))
    return [{"value": value, "score": round(score, 2)} for value, (score, _) in ranked[:_MAX_MATCHES]]


def _extract_column_values(rows: list[dict[str, Any]], column_name: str) -> list[str]:
    values: list[str] = []
    column_lower = column_name.lower()
    for row in rows:
        for key, val in row.items():
            if str(key).lower() == column_lower and val is not None:
                values.append(str(val))
                break
    return values


def _fetch_distinct_values(
    table_name: str,
    column_name: str,
    cube_address: str,
) -> list[str]:
    use_mock = os.getenv("SSAS_USE_MOCK", "false").lower() == "true"
    if use_mock:
        exact = _MOCK_DIMENSION_VALUES.get((table_name, column_name))
        if exact:
            return list(exact)
        # Fallback genérico: misma columna en cualquier tabla mock
        col_key = column_name.strip().lower()
        for (t, c), vals in _MOCK_DIMENSION_VALUES.items():
            if c.lower() == col_key:
                return list(vals)
        return []

    dax = _build_distinct_values_dax(table_name, column_name)
    rows = run_dax(cube_address, dax)
    return _extract_column_values(rows, column_name)


@tool
def lookup_dimension_values(
    table_name: str,
    column_name: str,
    search_hint: str = "",
    config: Annotated[RunnableConfig, InjectedToolArg] = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """
    Busca valores exactos en el cubo que coincidan con un filtro mencionado por el usuario.

    Úsala cuando la pregunta implique filtrar por país, región, cliente u otra categoría
    cuyo texto puede diferir del valor real del cubo (Perú vs PERU).
    No ejecuta la consulta final: solo resuelve el valor exacto del filtro.

    Args:
        table_name: Nombre de tabla del diccionario (ej. BI_FlotHs Mod01_Equipo).
        column_name: Columna de filtro (ej. Pais_Destino, Region_Destino).
        search_hint: Texto del usuario a buscar (ej. Perú, lima, chile). Nunca vacío.
    """
    hint = str(search_hint or "").strip()
    if not hint:
        return {
            "error": "search_hint vacío",
            "matches": [],
            "note": (
                "Obligatorio: pasa en search_hint el texto del filtro del usuario "
                "(ej. Perú, lima, chile). Vuelve a llamar la herramienta con ese valor."
            ),
        }

    cube_address = (config or {}).get("configurable", {}).get("cube_address", "")
    dictionary_rel = str((config or {}).get("configurable", {}).get("dictionary_path") or "")
    try:
        resolved_table, resolved_column = _resolve_table_column(
            table_name, column_name, dictionary_rel
        )
    except ValueError as exc:
        return {
            "error": str(exc),
            "search_hint": hint,
            "matches": [],
            "note": "Corrige table_name/column_name con nombres del diccionario de la fuente activa.",
        }

    try:
        distinct_values = _fetch_distinct_values(resolved_table, resolved_column, cube_address)
    except SSASConnectionError as exc:
        return {
            "error": str(exc),
            "table": resolved_table,
            "column": resolved_column,
            "search_hint": hint,
            "matches": [],
            "note": "No se pudo consultar el cubo; reintenta o usa un valor conocido del diccionario.",
        }

    matches = _find_matches(hint, distinct_values)
    return {
        "table": resolved_table,
        "column": resolved_column,
        "search_hint": hint,
        "matches": matches,
        "usage_hint": (
            "Use el campo 'value' de matches tal cual en DAX, por ejemplo: "
            f"FILTER('{resolved_table}', '{resolved_table}'[{resolved_column}] = \"VALOR_EXACTO\")"
        ),
        "note": (
            "Sin coincidencias: pruebe otra columna relacionada o un search_hint más corto "
            "(solo el país o región, sin palabras extra)."
            if not matches
            else "Use solo los valores listados; no invente variantes ortográficas."
        ),
    }
