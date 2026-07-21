"""
Catálogo editable de fuentes (cubo SSAS + Power BI + diccionario) desde CSV.
Archivo: agent_api/data/fuentes_datos.csv
Columnas: seudonimo,ruta_cubo,ruta_power_bi,ruta_diccionario
ruta_diccionario: ruta(s) relativa(s) a agent_api/, varias separadas por |
  (ej. metadata/diccionarios_cubos/t1.csv|metadata/diccionarios_cubos/t2.csv)
En cada CSV de diccionario, CUBE_TABLE_NAME (opcional) = nombre exacto de la tabla en el cubo DAX.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any

_AGENT_API_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _AGENT_API_ROOT / "data"
_CSV_PATH = Path(os.getenv("DATA_SOURCES_CSV_PATH", str(_DATA_DIR / "fuentes_datos.csv")))


def _normalize_cell(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text or text.lower() in {"none", "null", "n/a", "-"}:
        return None
    return text


def resolve_dictionary_path(relative: str | None) -> Path | None:
    """
    Resuelve una sola ruta_diccionario relativa a agent_api/.
    Acepta también rutas ya absolutas si existen.
    Si hay varias separadas por |, resuelve solo la primera (usar resolve_all_dictionary_paths).
    """
    paths = resolve_all_dictionary_paths(relative)
    return paths[0] if paths else None


def resolve_all_dictionary_paths(relative: str | None) -> list[Path]:
    """
    Resuelve una o varias rutas (separadas por |).
    Todas las partes deben existir para considerar el catálogo válido.
    """
    if not relative:
        return []
    found: list[Path] = []
    for part in relative.split("|"):
        text = part.strip().replace("\\", "/")
        if not text:
            continue
        resolved = _resolve_one_dictionary_path(text)
        if resolved is None:
            return []
        found.append(resolved)
    return found


def _resolve_one_dictionary_path(text: str) -> Path | None:
    candidate = Path(text)
    if candidate.is_file():
        return candidate.resolve()
    under_api = (_AGENT_API_ROOT / text).resolve()
    if under_api.is_file():
        return under_api
    under_meta = (_AGENT_API_ROOT / "metadata" / text).resolve()
    if under_meta.is_file():
        return under_meta
    return None


def dictionaries_exist(relative: str | None) -> bool:
    """True si todas las rutas (o la única) existen."""
    if not relative or not relative.strip():
        return False
    parts = [p.strip() for p in relative.split("|") if p.strip()]
    if not parts:
        return False
    return len(resolve_all_dictionary_paths(relative)) == len(parts)


def _parse_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            seudonimo = _normalize_cell(raw.get("seudonimo") or raw.get("seudónimo"))
            if not seudonimo:
                continue
            ruta_dicc = _normalize_cell(raw.get("ruta_diccionario"))
            rows.append(
                {
                    "seudonimo": seudonimo,
                    "ruta_cubo": _normalize_cell(raw.get("ruta_cubo")),
                    "ruta_power_bi": _normalize_cell(raw.get("ruta_power_bi")),
                    "ruta_diccionario": ruta_dicc,
                    "diccionario_existe": dictionaries_exist(ruta_dicc),
                }
            )
    return rows


def list_data_sources() -> list[dict[str, Any]]:
    return _parse_csv(_CSV_PATH)


def get_data_source(seudonimo: str | None) -> dict[str, Any] | None:
    if not seudonimo or not seudonimo.strip():
        return None
    key = seudonimo.strip().lower()
    for row in list_data_sources():
        if str(row.get("seudonimo", "")).strip().lower() == key:
            return row
    return None


def get_dictionary_path_for_seudonimo(seudonimo: str | None) -> str | None:
    """Devuelve la ruta relativa del diccionario para un seudónimo."""
    row = get_data_source(seudonimo)
    if not row:
        return None
    return row.get("ruta_diccionario")


def get_csv_path() -> str:
    return str(_CSV_PATH)
