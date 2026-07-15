"""
Diccionario del cubo Tabular SSAS.
Carga columnas y descripciones desde CSVs en metadata/diccionarios_cubos/.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from pydantic import BaseModel

DICCIONARIOS_DIR = Path(__file__).resolve().parent / "diccionarios_cubos"
DEFAULT_CUBE_NAME = "CB_BI_FlotHs"


class ColumnDefinition(BaseModel):
    name: str
    data_type: str = ""
    description: str = ""


class TableDefinition(BaseModel):
    name: str
    description: str = ""
    columns: list[ColumnDefinition]


class CubeSchema(BaseModel):
    cube_name: str = DEFAULT_CUBE_NAME
    tables: list[TableDefinition]


def quote_dax_table(table_name: str) -> str:
    """Formatea nombre de tabla para DAX (comillas si tiene espacios)."""
    return f"'{table_name}'" if " " in table_name else table_name


def quote_dax_column(table_name: str, column_name: str) -> str:
    """Formatea referencia tabla[columna] para DAX."""
    return f"{quote_dax_table(table_name)}[{column_name}]"


def _infer_table_name_from_csv(filename: str, rows: list[dict[str, str]]) -> str:
    """Infiere el nombre SSAS de la tabla desde el CSV."""
    if rows:
        owner = rows[0].get("TABLE_OWNER", "").strip()
        table = rows[0].get("TABLE_NAME", "").strip()
        if owner and table:
            return f"{owner} {table}"

    match = re.search(r"diccionario_datos_cubo_(.+)\.csv$", filename, re.IGNORECASE)
    if match:
        # BI_FlotHs_Mod01_Equipo → BI_FlotHs Mod01_Equipo (solo el primer _ separa owner de tabla)
        parts = match.group(1).split("_", 1)
        if len(parts) == 2:
            return f"{parts[0]} {parts[1].replace('_', ' ')}"
        return match.group(1).replace("_", " ")

    return "TablaDesconocida"


def _load_table_from_csv(csv_path: Path) -> TableDefinition:
    """Carga una tabla y sus columnas desde un archivo CSV de diccionario."""
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        raw_rows = list(reader)

    table_name = _infer_table_name_from_csv(csv_path.name, raw_rows)
    columns: list[ColumnDefinition] = []

    for row in raw_rows:
        col_name = row.get("COLUMN_NAME", "").strip()
        if not col_name:
            continue
        columns.append(
            ColumnDefinition(
                name=col_name,
                data_type=row.get("TIPO_VARIABLE", "").strip(),
                description=row.get("DESCRIPCION", "").strip(),
            )
        )

    descriptions = [c.description for c in columns if c.description]
    table_desc = descriptions[0] if len(descriptions) == 1 else (
        f"Tabla del cubo con {len(columns)} columnas documentadas."
    )

    return TableDefinition(name=table_name, description=table_desc, columns=columns)


def load_cube_schema(cube_name: str = DEFAULT_CUBE_NAME) -> CubeSchema:
    """Construye el esquema del cubo leyendo todos los CSV en diccionarios_cubos/."""
    tables: list[TableDefinition] = []

    if DICCIONARIOS_DIR.exists():
        for csv_file in sorted(DICCIONARIOS_DIR.glob("diccionario_datos_cubo_*.csv")):
            tables.append(_load_table_from_csv(csv_file))

    if not tables:
        tables.append(
            TableDefinition(
                name="BI_FlotHs Mod01_Equipo",
                description="Tabla de equipos (sin CSV de diccionario cargado).",
                columns=[],
            )
        )

    return CubeSchema(cube_name=cube_name, tables=tables)


CUBE_SCHEMA = load_cube_schema()


def get_cube_dictionary_prompt() -> str:
    """Genera el bloque de texto inyectado en el System Prompt del LLM."""
    schema = load_cube_schema()
    lines: list[str] = [
        f"Cubo: {schema.cube_name}",
        "",
        "TABLAS Y COLUMNAS DISPONIBLES (fuente: diccionarios CSV):",
    ]

    for table in schema.tables:
        dax_table = quote_dax_table(table.name)
        lines.append(f"\n  Tabla: {table.name}")
        lines.append(f"  Referencia DAX: {dax_table}")
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

    lines.extend([
        "",
        "MEDIDAS DISPONIBLES:",
        "  Este cubo no define medidas DAX explícitas. Usa funciones de agregación",
        "  sobre columnas: COUNTROWS, DISTINCTCOUNT, SUM, AVERAGE según el tipo.",
        "",
        "REGLAS DAX OBLIGATORIAS:",
        "- Usa ÚNICAMENTE tablas y columnas listadas arriba.",
        "- Tablas con espacios van entre comillas simples: 'BI_FlotHs Mod01_Equipo'.",
        "- Columnas: 'BI_FlotHs Mod01_Equipo'[Pais_Destino]",
        "- Las consultas deben comenzar con EVALUATE.",
        "- Para conteos: EVALUATE ROW(\"Total\", COUNTROWS('Tabla'))",
        "- Para agrupaciones: EVALUATE SUMMARIZECOLUMNS('Tabla'[Columna], \"Total\", COUNTROWS('Tabla'))",
        "- Para top N: EVALUATE TOPN(10, SUMMARIZECOLUMNS(...), [Medida])",
        "- Para filtros: EVALUATE FILTER('Tabla', 'Tabla'[Columna] = \"valor\")",
    ])

    return "\n".join(lines)


def get_all_column_names() -> list[str]:
    """Devuelve todos los nombres de columna documentados."""
    schema = load_cube_schema()
    return [col.name for table in schema.tables for col in table.columns]
