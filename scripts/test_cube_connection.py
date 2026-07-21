#!/usr/bin/env python
"""
Script de prueba de conexión y consultas DAX contra un cubo Tabular SSAS.

Cubo configurado por defecto: CB_BI_FlotHs @ 10.0.57.86

Uso básico – conexión + COUNT de BI_FlotHs Mod01_Equipo:
  conda activate py312da
  python scripts/test_cube_connection.py

Solo COUNT (sin test de conexión previo):
  python scripts/test_cube_connection.py --count-only

Descubrir tablas, columnas y muestra de datos del cubo:
  python scripts/test_cube_connection.py --discover
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent_api.tools.ssas_client import SSASConnectionError, execute_dax_query, test_connection

# ---------------------------------------------------------------------------
# Configuración del cubo CB_BI_FlotHs
# ---------------------------------------------------------------------------
DEFAULT_CUBE_ADDRESS = (
    "Provider=MSOLAP;Data Source=10.0.57.86;Initial Catalog=CB_BI_FlotHs;"
)

# Tabla real (los espacios requieren comillas simples en DAX)
TABLE_EQUIPO = "'BI_FlotHs Mod01_Equipo'"

# Consulta COUNT de todos los registros
COUNT_QUERY = f'EVALUATE ROW("Total registros", COUNTROWS({TABLE_EQUIPO}))'

DEFAULT_QUERIES: dict[str, str] = {
    "conteo_equipos": COUNT_QUERY,
}

# Consultas de descubrimiento compatibles con SSAS Tabular on-prem
# (INFO.TABLES/MEASURES/COLUMNS solo funcionan en Power BI, no en SSAS clásico)
DISCOVERY_QUERIES: dict[str, str] = {
    "01_listar_tablas": "SELECT TABLE_NAME FROM $SYSTEM.DBSCHEMA_TABLES",
    "02_conteo_equipos": COUNT_QUERY,
    "03_muestra_equipos": f"EVALUATE TOPN(5, {TABLE_EQUIPO})",
}

# Ruta al diccionario de columnas (carpeta oficial de diccionarios)
COLUMNS_CSV_DIR = PROJECT_ROOT / "agent_api" / "metadata" / "diccionarios_cubos"

# Consultas de negocio del cubo CI_BI_FlotHs
BUSINESS_QUERIES: dict[str, str] = {
    **DEFAULT_QUERIES,
    "03_conteo_equipos_detalle": (
        f'EVALUATE SUMMARIZECOLUMNS({TABLE_EQUIPO}, "Total", COUNTROWS({TABLE_EQUIPO}))'
    ),
}


def _load_cube_address_from_env_file() -> str | None:
    env_file = Path(__file__).parent / ".env.cube"
    if not env_file.exists():
        return None

    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("CUBE_ADDRESS="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _resolve_cube_address(cli_value: str | None) -> str:
    address = (
        cli_value
        or os.getenv("CUBE_ADDRESS")
        or _load_cube_address_from_env_file()
        or DEFAULT_CUBE_ADDRESS
    )
    if not address:
        raise SSASConnectionError(
            "No se encontró la cadena de conexión.\n"
            "Use --cube-address, scripts/.env.cube o la variable CUBE_ADDRESS"
        )
    return address


def _print_results(label: str, rows: list[dict[str, Any]], max_rows: int = 25) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {label}")
    print(f"{'=' * 70}")

    if not rows:
        print("  (sin filas)")
        return

    columns = list(rows[0].keys())
    # Ancho suficiente para no truncar nombres de tabla SSAS (ej. TH_PedidoVersModif)
    col_width = min(48, max(16, max(len(str(c)) for c in columns)))
    for row in rows[: min(max_rows, 5)]:
        for col in columns:
            col_width = max(col_width, min(48, len(str(row.get(col, "")))))
    header = " | ".join(f"{str(col)[:col_width]:<{col_width}}" for col in columns)
    print(header)
    print("-" * len(header))

    displayed = rows[:max_rows]
    for row in displayed:
        line = " | ".join(
            f"{str(row.get(col, ''))[:col_width]:<{col_width}}" for col in columns
        )
        print(line)

    if len(rows) > max_rows:
        print(f"\n  ... {len(rows) - max_rows} filas más (use --query para consultas específicas)")

    print(f"\n  Total filas: {len(rows)}")


def _parse_column_names_from_rows(rows: list[dict[str, Any]]) -> list[str]:
    """Extrae nombres de columna desde claves como Tabla[Columna]."""
    if not rows:
        return []
    columns: list[str] = []
    for key in rows[0]:
        match = re.search(r"\[([^\]]+)\]$", str(key))
        columns.append(match.group(1) if match else str(key))
    return columns


def _load_columns_from_csv() -> list[dict[str, str]]:
    """Lee columnas y descripciones de todos los CSV en diccionarios_cubos/."""
    columns: list[dict[str, str]] = []

    if not COLUMNS_CSV_DIR.exists():
        return columns

    for csv_path in sorted(COLUMNS_CSV_DIR.glob("diccionario_datos_cubo_*.csv")):
        with csv_path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=";")
            for row in reader:
                col_name = row.get("COLUMN_NAME", "").strip()
                if not col_name:
                    continue
                columns.append({
                    "tabla": csv_path.stem.replace("diccionario_datos_cubo_", "").replace("_", " "),
                    "columna": col_name,
                    "tipo": row.get("TIPO_VARIABLE", "").strip(),
                    "descripcion": row.get("DESCRIPCION", "").strip(),
                })
    return columns


def _print_csv_columns() -> None:
    """Imprime columnas documentadas en los CSV del cubo."""
    columns = _load_columns_from_csv()
    print(f"\n{'=' * 70}")
    print("  04_columnas_desde_csv (diccionarios_cubos/)")
    print(f"{'=' * 70}")

    if not columns:
        print(f"  No se encontraron CSV en: {COLUMNS_CSV_DIR}")
        return

    print(f"{'Columna':<35} | {'Tipo':<12} | Descripción")
    print("-" * 90)
    for col in columns:
        desc = col["descripcion"][:40]
        print(f"{col['columna']:<35} | {col['tipo']:<12} | {desc}")
    print(f"\n  Total columnas documentadas: {len(columns)}")


def _print_discovered_columns(rows: list[dict[str, Any]]) -> None:
    """Imprime columnas detectadas desde una muestra TOPN."""
    columns = _parse_column_names_from_rows(rows)
    print(f"\n{'=' * 70}")
    print("  Columnas detectadas desde muestra TOPN")
    print(f"{'=' * 70}")
    for col in columns:
        print(f"  - {col}")
    print(f"\n  Total columnas: {len(columns)}")


def _run_query(cube_address: str, name: str, dax: str, max_rows: int = 25) -> tuple[bool, list[dict[str, Any]]]:
    print(f"\n>> Ejecutando: {name}")
    print(f"   DAX: {dax}")
    try:
        rows = execute_dax_query(cube_address, dax)
        _print_results(name, rows, max_rows=max_rows)
        print("   [OK]")
        return True, rows
    except SSASConnectionError as exc:
        print(f"   [ERROR] {exc}")
        return False, []


def _run_query_set(cube_address: str, queries: dict[str, str]) -> tuple[int, int]:
    results = [_run_query(cube_address, name, dax)[0] for name, dax in queries.items()]
    passed = sum(results)
    return passed, len(results)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prueba de conexión y consultas DAX – cubo CI_BI_FlotHs.",
    )
    parser.add_argument(
        "--cube-address",
        help="Cadena ADOMD. Por defecto lee scripts/.env.cube",
    )
    parser.add_argument("--query", help="Consulta DAX personalizada.")
    parser.add_argument(
        "--count-only",
        action="store_true",
        help="Solo ejecuta COUNTROWS de BI_FlotHs Mod01_Equipo.",
    )
    parser.add_argument(
        "--ping-only",
        action="store_true",
        help="Solo valida la conexión.",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Lista tablas, COUNT, muestra de datos y columnas del cubo.",
    )
    parser.add_argument(
        "--run-business",
        action="store_true",
        help="Ejecuta consultas de negocio de ejemplo (requiere esquema VentasCube).",
    )
    parser.add_argument(
        "--list-samples",
        action="store_true",
        help="Muestra las consultas disponibles.",
    )

    args = parser.parse_args()

    if args.list_samples:
        print("Consultas por defecto (CI_BI_FlotHs):\n")
        for name, dax in DEFAULT_QUERIES.items():
            print(f"  {name}: {dax}")
        print("\nDescubrimiento completo (--discover):\n")
        for name, dax in DISCOVERY_QUERIES.items():
            print(f"  {name}: {dax}")
        print("\nNegocio de ejemplo (--run-business):\n")
        for name, dax in BUSINESS_QUERIES.items():
            print(f"  {name}: {dax}")
        return 0

    cube_address = _resolve_cube_address(args.cube_address)

    print("Prueba de cubo Tabular SSAS")
    print(f"Python:  {sys.executable}")
    print(f"Cubo:    CB_BI_FlotHs")
    print(f"Tabla:   BI_FlotHs Mod01_Equipo")
    print(f"Conexión: {cube_address}")

    if args.count_only:
        print("\n>> Ejecutando COUNT de todos los registros...")
        ok, _ = _run_query(cube_address, "conteo_equipos", COUNT_QUERY)
        return 0 if ok else 1

    # 1. Probar conexión
    print("\n>> Paso 1: Validando conexión...")
    try:
        ping_rows = test_connection(cube_address)
        _print_results("Test de conexión", ping_rows)
        print("   [OK] Conexión establecida")
    except SSASConnectionError as exc:
        print(f"   [ERROR] No se pudo conectar:\n   {exc}")
        return 1

    if args.ping_only:
        print("\nConexión verificada.")
        return 0

    if args.query:
        ok, _ = _run_query(cube_address, "Consulta personalizada", args.query)
        return 0 if ok else 1

    if args.discover:
        print("\n>> Paso 2: Descubrimiento del esquema del cubo...")
        passed = 0
        total = len(DISCOVERY_QUERIES)
        sample_rows: list[dict[str, Any]] = []

        for name, query in DISCOVERY_QUERIES.items():
            max_rows = 15 if name == "01_listar_tablas" else 25
            ok, rows = _run_query(cube_address, name, query, max_rows=max_rows)
            if ok:
                passed += 1
            if name == "03_muestra_equipos":
                sample_rows = rows

        if sample_rows:
            _print_discovered_columns(sample_rows)

        _print_csv_columns()
        if COLUMNS_CSV_DIR.exists() and list(COLUMNS_CSV_DIR.glob("diccionario_datos_cubo_*.csv")):
            passed += 1
            total += 1

        print(f"\nResumen: {passed}/{total} pasos exitosos")
        return 0 if passed == total else 1

    if args.run_business:
        print("\n>> Paso 2: Consultas de negocio (CI_BI_FlotHs – BI_FlotHs Mod01_Equipo)...")
        passed, total = _run_query_set(cube_address, BUSINESS_QUERIES)
        print(f"\nResumen: {passed}/{total} consultas exitosas")
        return 0 if passed == total else 1

    # 2. COUNT de registros
    print("\n>> Paso 2: COUNT de BI_FlotHs Mod01_Equipo...")
    print(f"   DAX: {COUNT_QUERY}")
    ok, _ = _run_query(cube_address, "conteo_equipos", COUNT_QUERY)

    if ok:
        print("\nListo.")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
