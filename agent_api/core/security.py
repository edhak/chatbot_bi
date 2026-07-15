"""
Validaciones de seguridad para consultas del agente BI.
"""

from __future__ import annotations

import os
import re

MAX_QUESTION_LENGTH = 500
MAX_DAX_LENGTH = 4_000
MAX_RESULT_ROWS = 200

# Solo consultas de lectura; bloquea DDL/DML y funciones peligrosas
_FORBIDDEN_DAX = re.compile(
    r"\b("
    r"DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|EXEC|EXECUTE|"
    r"OPENROWSET|OPENDATASOURCE|BULK|xp_|sp_|"
    r"EVALUATE\s+INFO\s*\.\s*TABLES|SYSTEM\s*\.\s*DISCOVER"
    r")\b",
    re.IGNORECASE,
)

_CUBE_ADDRESS_PATTERN = re.compile(
    r"^Provider\s*=\s*MSOLAP\s*;",
    re.IGNORECASE,
)


def get_allowed_cube_address(requested: str | None) -> str:
    """
    Usa la cadena del servidor por defecto.
    Solo acepta override del cliente si ALLOW_CLIENT_CUBE_ADDRESS=true.
    """
    default = os.getenv(
        "DEFAULT_CUBE_ADDRESS",
        "Provider=MSOLAP;Data Source=10.0.57.86;Initial Catalog=CB_BI_FlotHs;",
    ).strip()
    allow_override = os.getenv("ALLOW_CLIENT_CUBE_ADDRESS", "false").lower() == "true"

    if not allow_override or not requested or not requested.strip():
        return default

    candidate = requested.strip()
    if len(candidate) > 500:
        raise ValueError("La cadena de conexión al cubo es demasiado larga.")
    if not _CUBE_ADDRESS_PATTERN.match(candidate):
        raise ValueError("Formato de conexión al cubo no permitido.")
    if "password=" in candidate.lower() or "pwd=" in candidate.lower():
        raise ValueError("No se permiten credenciales en la cadena de conexión.")

    return candidate


def validate_question(question: str) -> str:
    text = question.strip()
    if not text:
        raise ValueError("La pregunta no puede estar vacía.")
    if len(text) > MAX_QUESTION_LENGTH:
        raise ValueError(f"La pregunta no puede superar {MAX_QUESTION_LENGTH} caracteres.")
    return text


def validate_dax_query(dax_query: str) -> str:
    text = dax_query.strip()
    if not text:
        raise ValueError("La consulta DAX está vacía.")
    if len(text) > MAX_DAX_LENGTH:
        raise ValueError(f"La consulta DAX no puede superar {MAX_DAX_LENGTH} caracteres.")
    if not text.upper().startswith("EVALUATE"):
        raise ValueError("Solo se permiten consultas DAX que comiencen con EVALUATE.")
    if _FORBIDDEN_DAX.search(text):
        raise ValueError("La consulta DAX contiene operaciones no permitidas.")
    return text


def truncate_rows(rows: list[dict], limit: int = MAX_RESULT_ROWS) -> list[dict]:
    if len(rows) <= limit:
        return rows
    return rows[:limit]
