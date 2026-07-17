"""
Cliente de conexión a cubos Tabular SSAS vía ADOMD (pyadomd).
Reutilizable desde scripts de prueba y desde el executor del agente.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

ADOMD_DLL_NAME = "Microsoft.AnalysisServices.AdomdClient.dll"

# Rutas típicas donde Windows instala ADOMD.NET
ADOMD_SEARCH_PATHS: list[Path] = [
    Path(r"C:\Program Files\Microsoft.NET\ADOMD.NET\160"),
    Path(r"C:\Program Files (x86)\Microsoft.NET\ADOMD.NET\160"),
    Path(r"C:\Program Files\Microsoft.NET\ADOMD.NET\150"),
    Path(r"C:\Program Files (x86)\Microsoft.NET\ADOMD.NET\150"),
    Path(r"C:\Program Files\Microsoft SQL Server\MSAS16.MSSQLSERVER\OLAP\bin"),
    Path(r"C:\Program Files\Microsoft SQL Server\MSAS15.MSSQLSERVER\OLAP\bin"),
]

_adomd_configured = False
_COLUMN_KEY_PATTERN = re.compile(r"\[([^\]]+)\]$")


_CLR_INT_TYPES = {
    "Int16", "Int32", "Int64", "UInt16", "UInt32", "UInt64",
    "Byte", "SByte", "SqlInt16", "SqlInt32", "SqlInt64", "SqlByte",
}
_CLR_FLOAT_TYPES = {
    "Single", "Double", "Decimal", "SqlDecimal", "SqlSingle", "SqlDouble", "SqlMoney",
}


def _normalize_cell(value: Any) -> Any:
    """Convierte valores CLR/.NET a tipos JSON-serializables (int/float/str)."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, float):
        return float(value)
    try:
        from decimal import Decimal

        if isinstance(value, Decimal):
            return float(value)
    except Exception:
        pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass

    type_name = type(value).__name__
    if type_name in _CLR_INT_TYPES:
        try:
            return int(str(value).strip())
        except Exception:
            try:
                return int(value)  # type: ignore[arg-type]
            except Exception:
                return str(value)
    if type_name in _CLR_FLOAT_TYPES:
        try:
            return float(str(value).strip().replace(",", ""))
        except Exception:
            try:
                return float(value)  # type: ignore[arg-type]
            except Exception:
                return str(value)
    if type_name in {"DateTime", "Date", "TimeSpan", "SqlDateTime"}:
        return str(value)

    # Último intento: números empaquetados por pythonnet
    try:
        as_float = float(value)  # type: ignore[arg-type]
        if as_float == int(as_float) and abs(as_float) < 1e15:
            return int(as_float)
        return as_float
    except Exception:
        pass
    return value


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convierte claves 'Tabla[Columna]' a 'Columna' y valores a tipos JSON-safe."""
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        match = _COLUMN_KEY_PATTERN.search(str(key))
        clean_key = match.group(1) if match else str(key)
        normalized[clean_key] = _normalize_cell(value)
    return normalized


class SSASConnectionError(Exception):
    """Error de conexión o ejecución contra SSAS Tabular."""


def find_adomd_client_path() -> Path | None:
    """Busca Microsoft.AnalysisServices.AdomdClient.dll en rutas conocidas."""
    for folder in ADOMD_SEARCH_PATHS:
        dll = folder / ADOMD_DLL_NAME
        if dll.exists():
            return dll
    return None


def _ensure_adomd_runtime() -> None:
    """
    Configura PATH y referencia CLR para que pyadomd encuentre AdomdClient.dll.
    Debe ejecutarse ANTES de importar pyadomd.
    """
    global _adomd_configured
    if _adomd_configured:
        return

    dll_path = find_adomd_client_path()
    if dll_path is None:
        raise SSASConnectionError(
            "No se encontró Microsoft.AnalysisServices.AdomdClient.dll.\n"
            "Instale ADOMD.NET (SQL Server Feature Pack o SSMS) y reinicie la terminal.\n"
            "Rutas buscadas:\n"
            + "\n".join(f"  - {p}" for p in ADOMD_SEARCH_PATHS)
        )

    adomd_dir = str(dll_path.parent)
    if adomd_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = adomd_dir + os.pathsep + os.environ.get("PATH", "")

    try:
        import clr  # type: ignore[import-untyped]  # pythonnet

        clr.AddReference(str(dll_path))
    except Exception:
        # Si clr falla, confiamos en que PATH sea suficiente para pyadomd
        pass

    _adomd_configured = True


def _import_pyadomd():
    """Importa Pyadomd con mensajes de error claros."""
    try:
        _ensure_adomd_runtime()
        from pyadomd import Pyadomd

        return Pyadomd
    except SSASConnectionError:
        raise
    except ImportError as exc:
        python_exe = sys.executable
        raise SSASConnectionError(
            "pyadomd no está instalado en el Python actual.\n"
            f"  Python en uso: {python_exe}\n"
            "  Solución:\n"
            "    conda activate py312da\n"
            '    pip install -e ".[ssas]"\n'
            "  Luego ejecute el script con ese mismo entorno (no Python 3.14 u otro)."
        ) from exc
    except Exception as exc:
        error_text = str(exc)
        if "AdomdClient" in error_text or "AdomdConnection" in error_text:
            dll = find_adomd_client_path()
            hint = f"\n  DLL detectada en: {dll}" if dll else ""
            raise SSASConnectionError(
                "ADOMD.NET está instalado pero Python no pudo cargar AdomdClient.dll.\n"
                f"  Python en uso: {sys.executable}{hint}\n"
                "  Use el entorno conda py312da y reinicie la terminal."
            ) from exc
        raise SSASConnectionError(f"Error al inicializar pyadomd: {exc}") from exc


def execute_dax_query(cube_address: str, dax_query: str) -> list[dict[str, Any]]:
    """
    Ejecuta una consulta DAX contra un cubo Tabular SSAS.

    Args:
        cube_address: Cadena de conexión ADOMD.
        dax_query: Consulta DAX (EVALUATE ...).

    Returns:
        Lista de registros como diccionarios {columna: valor}.
    """
    Pyadomd = _import_pyadomd()

    if not cube_address.strip():
        raise SSASConnectionError("La cadena de conexión (cube_address) está vacía.")

    if not dax_query.strip():
        raise SSASConnectionError("La consulta DAX está vacía.")

    try:
        with Pyadomd(cube_address) as conn:
            with conn.cursor().execute(dax_query) as cursor:
                if cursor.description is None:
                    return []

                columns = [
                    col[0].name if hasattr(col[0], "name") else str(col[0])
                    for col in cursor.description
                ]
                rows = [_normalize_row(dict(zip(columns, row))) for row in cursor.fetchall()]
                return rows

    except SSASConnectionError:
        raise
    except Exception as exc:
        raise SSASConnectionError(f"Error al ejecutar DAX: {exc}") from exc


def test_connection(cube_address: str) -> list[dict[str, Any]]:
    """Ejecuta una consulta mínima para validar conectividad."""
    return execute_dax_query(
        cube_address,
        'EVALUATE ROW("Estado", "Conexión OK")',
    )
