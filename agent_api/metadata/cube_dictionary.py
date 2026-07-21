"""
Diccionario del cubo Tabular SSAS.
Carga columnas y descripciones desde CSVs (ruta relativa por fuente).
"""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

DICCIONARIOS_DIR = Path(__file__).resolve().parent / "diccionarios_cubos"
DEFAULT_CUBE_NAME = "CB_BI_FlotHs"
# Fallback si no se indica fuente
_DEFAULT_DICT_REL = "metadata/diccionarios_cubos/diccionario_datos_cubo_BI_FlotHs_Mod01_Equipo.csv"


class ColumnDefinition(BaseModel):
    name: str
    data_type: str = ""
    description: str = ""


class TableDefinition(BaseModel):
    name: str
    description: str = ""
    columns: list[ColumnDefinition]
    # Nombres de negocio / TABLE_NAME del CSV (para resolver lookups si el LLM usa el lógico)
    aliases: list[str] = []


class CubeSchema(BaseModel):
    cube_name: str = DEFAULT_CUBE_NAME
    tables: list[TableDefinition]
    dictionary_path: str = ""


def quote_dax_table(table_name: str) -> str:
    """Formatea nombre de tabla para DAX (comillas si tiene espacios)."""
    return f"'{table_name}'" if " " in table_name else table_name


def quote_dax_column(table_name: str, column_name: str) -> str:
    """Formatea referencia tabla[columna] para DAX."""
    return f"{quote_dax_table(table_name)}[{column_name}]"


# Nombre DAX exacto en el cubo Tabular (prioridad sobre TABLE_OWNER/TABLE_NAME).
_CUBE_TABLE_KEYS = (
    "CUBE_TABLE_NAME",
    "NOMBRE_TABLA_CUBO",
    "TABLA_CUBO",
    "DAX_TABLE_NAME",
)


def _cell(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = (row.get(key) or "").strip()
        if value:
            return value
    return ""


def _infer_table_name_from_csv(filename: str, rows: list[dict[str, str]]) -> str:
    """
    Nombre de tabla para DAX (el que debe existir en el cubo SSAS).

    Prioridad:
      1) CUBE_TABLE_NAME / NOMBRE_TABLA_CUBO / TABLA_CUBO / DAX_TABLE_NAME
      2) TABLE_OWNER + ' ' + TABLE_NAME (legado FlotHs)
      3) Inferencia desde el nombre del archivo
    """
    if rows:
        cube_name = _cell(rows[0], *_CUBE_TABLE_KEYS)
        if cube_name:
            return cube_name

        owner = _cell(rows[0], "TABLE_OWNER")
        table = _cell(rows[0], "TABLE_NAME")
        if owner and table:
            return f"{owner} {table}"
        if table:
            return table

    stem = Path(filename).stem
    match = re.search(r"diccionario_datos_cubo_(.+)$", stem, re.IGNORECASE)
    if match:
        raw = match.group(1)
        # Quitar sufijo " copy" / similares del nombre de archivo
        raw = re.sub(r"\s+copy$", "", raw, flags=re.IGNORECASE)
        parts = raw.split("_", 1)
        if len(parts) == 2:
            return f"{parts[0]} {parts[1].replace('_', ' ')}"
        return raw.replace("_", " ")

    return "TablaDesconocida"


def _logical_label_from_rows(rows: list[dict[str, str]]) -> str:
    """Etiqueta de negocio (TABLE_OWNER/TABLE_NAME) si difiere del nombre DAX."""
    if not rows:
        return ""
    owner = _cell(rows[0], "TABLE_OWNER")
    table = _cell(rows[0], "TABLE_NAME")
    if owner and table:
        return f"{owner} {table}"
    return table


def _load_table_from_csv(csv_path: Path) -> TableDefinition:
    """Carga una tabla y sus columnas desde un archivo CSV de diccionario."""
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        raw_rows = list(reader)

    table_name = _infer_table_name_from_csv(csv_path.name, raw_rows)
    logical = _logical_label_from_rows(raw_rows)
    aliases: list[str] = []
    if raw_rows:
        owner = _cell(raw_rows[0], "TABLE_OWNER")
        table_only = _cell(raw_rows[0], "TABLE_NAME")
        for alias in (logical, table_only, f"{owner}_{table_only}" if owner and table_only else ""):
            a = alias.strip()
            if a and a.lower() != table_name.lower() and a not in aliases:
                aliases.append(a)

    columns: list[ColumnDefinition] = []

    for row in raw_rows:
        col_name = _cell(row, "COLUMN_NAME")
        if not col_name:
            continue
        columns.append(
            ColumnDefinition(
                name=col_name,
                data_type=_cell(row, "TIPO_VARIABLE"),
                description=_cell(row, "DESCRIPCION"),
            )
        )

    descriptions = [c.description for c in columns if c.description]
    table_desc = descriptions[0] if len(descriptions) == 1 else (
        f"Tabla del cubo con {len(columns)} columnas documentadas."
    )
    if logical and logical != table_name:
        table_desc = (
            f"Nombre DAX en cubo (OBLIGATORIO en consultas): {table_name}. "
            f"Diccionario lógico: {logical}. {table_desc}"
        )

    return TableDefinition(
        name=table_name,
        description=table_desc,
        columns=columns,
        aliases=aliases,
    )


def _paths_from_relative(dictionary_rel: str | None) -> list[Path]:
    """Una o varias rutas de diccionario. Soporta varias separadas por |."""
    key = (dictionary_rel or "").strip()
    if not key:
        # Sin ruta explícita: usar el primer diccionario del catálogo de fuentes
        try:
            from agent_api.core.data_sources import list_data_sources

            for row in list_data_sources():
                rel = row.get("ruta_diccionario")
                if rel:
                    from agent_api.core.data_sources import resolve_all_dictionary_paths

                    paths = resolve_all_dictionary_paths(str(rel))
                    if paths:
                        return paths
        except Exception:
            pass
        from agent_api.core.data_sources import resolve_all_dictionary_paths

        return resolve_all_dictionary_paths(_DEFAULT_DICT_REL)

    from agent_api.core.data_sources import resolve_all_dictionary_paths

    return resolve_all_dictionary_paths(key)


@lru_cache(maxsize=32)
def load_cube_schema(dictionary_rel: str = "") -> CubeSchema:
    """
    Carga el esquema desde ruta(s) relativa(s) de diccionario.
    dictionary_rel vacío → primer diccionario de fuentes_datos.csv (o fallback).
    Varias rutas: separar con |.
    """
    key = (dictionary_rel or "").strip()
    paths = _paths_from_relative(key or None)
    tables: list[TableDefinition] = []
    used: list[str] = []

    for path in paths:
        tables.append(_load_table_from_csv(path))
        used.append(str(path))

    if not tables and key:
        # Ruta pedida explícitamente pero no existe: no inventar otro diccionario
        return CubeSchema(
            cube_name="SIN_DICCIONARIO",
            tables=[],
            dictionary_path=key,
        )

    if not tables and DICCIONARIOS_DIR.exists():
        for csv_file in sorted(DICCIONARIOS_DIR.glob("diccionario_datos_cubo_*.csv")):
            if "prueba" in csv_file.name.lower():
                continue
            tables.append(_load_table_from_csv(csv_file))
            used.append(str(csv_file))
            break

    cube_name = DEFAULT_CUBE_NAME
    if tables:
        first = tables[0].name.split(" ", 1)[0] if tables[0].name else DEFAULT_CUBE_NAME
        cube_name = first if first else DEFAULT_CUBE_NAME

    return CubeSchema(
        cube_name=cube_name,
        tables=tables,
        dictionary_path=" | ".join(used),
    )


def get_cube_dictionary_prompt(dictionary_rel: str = "") -> str:
    """Bloque de texto inyectado en el System Prompt según el diccionario de la fuente."""
    schema = load_cube_schema(dictionary_rel or "")
    sample_table = schema.tables[0].name if schema.tables else "Tabla"
    sample_col = (
        schema.tables[0].columns[0].name
        if schema.tables and schema.tables[0].columns
        else "Columna"
    )
    dax_table = quote_dax_table(sample_table)

    lines: list[str] = [
        f"Cubo / modelo: {schema.cube_name}",
        f"Diccionario: {schema.dictionary_path or '(por defecto)'}",
        "",
        "TABLAS Y COLUMNAS DISPONIBLES (fuente: diccionario CSV de esta fuente):",
    ]

    for table in schema.tables:
        qt = quote_dax_table(table.name)
        lines.append(f"\n  Tabla: {table.name}")
        lines.append(f"  Referencia DAX: {qt}  ← usar ESTE nombre en EVALUATE")
        if table.aliases:
            lines.append(f"  Alias de diccionario (NO usar en DAX): {', '.join(table.aliases)}")
        if table.description:
            lines.append(f"  Descripción: {table.description}")

        if table.columns:
            lines.append("  Columnas:")
            for col in table.columns:
                dax_col = quote_dax_column(table.name, col.name)
                tipo = f" ({col.data_type})" if col.data_type else ""
                desc = f" – {col.description}" if col.description else ""
                lines.append(f"    - {dax_col}{tipo}{desc}")
        else:
            lines.append("  Columnas: (no documentadas en CSV)")

    # Columnas que parecen categóricas (para hint genérico de lookup)
    geo_like = []
    for table in schema.tables:
        for col in table.columns:
            low = col.name.lower()
            if any(k in low for k in ("pais", "region", "mercado", "cliente", "ciudad", "estado")):
                geo_like.append(quote_dax_column(table.name, col.name))
    geo_hint = ", ".join(geo_like[:8]) if geo_like else "(revisa columnas categóricas del listado)"

    lines.extend([
        "",
        "MEDIDAS DISPONIBLES:",
        "  Si el diccionario no lista medidas DAX explícitas, usa agregaciones",
        "  sobre columnas: COUNTROWS, DISTINCTCOUNT, SUM, AVERAGE según el tipo.",
        "",
        "REGLAS DAX OBLIGATORIAS:",
        "- Usa ÚNICAMENTE tablas y columnas listadas arriba (de ESTE diccionario).",
        f"- Tablas con espacios: comillas simples, ej. {dax_table}.",
        f"- Columnas: {quote_dax_column(sample_table, sample_col)}",
        "- Toda consulta debe iniciar con EVALUATE.",
        f'- Conteos: EVALUATE ROW("Total", COUNTROWS({dax_table}))',
        f"- Agrupaciones: EVALUATE SUMMARIZECOLUMNS({quote_dax_column(sample_table, sample_col)}, \"Total\", COUNTROWS({dax_table}))",
        "- Top N: EVALUATE TOPN(10, SUMMARIZECOLUMNS(...), [Medida], DESC)",
        f"- Filtros: EVALUATE FILTER({dax_table}, {quote_dax_column(sample_table, sample_col)} = \"valor\")",
        "",
        "FILTROS POR VALORES CATEGÓRICOS:",
        "- Si la pregunta menciona un filtro (país, región, cliente, etc.), NO adivines el valor.",
        "- PRIMERO llama lookup_dimension_values (tabla, columna, search_hint corto).",
        "- Usa en DAX los valores EXACTOS devueltos por el lookup.",
        f"- Columnas categóricas frecuentes en este modelo: {geo_hint}",
        "- NO llames execute_dax_query: otro nodo ejecuta el DAX. Solo genera la consulta.",
    ])

    return "\n".join(lines)


def get_all_column_names(dictionary_rel: str = "") -> list[str]:
    """Devuelve todos los nombres de columna documentados para la fuente."""
    schema = load_cube_schema(dictionary_rel or "")
    return [col.name for table in schema.tables for col in table.columns]
