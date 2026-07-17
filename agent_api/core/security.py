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
    default = os.getenv("DEFAULT_CUBE_ADDRESS", "").strip()
    use_mock = os.getenv("SSAS_USE_MOCK", "false").lower() == "true"
    allow_override = os.getenv("ALLOW_CLIENT_CUBE_ADDRESS", "false").lower() == "true"

    if not allow_override or not requested or not requested.strip():
        return _resolve_cube_address(default, use_mock=use_mock)

    candidate = requested.strip()
    if len(candidate) > 500:
        raise ValueError("La cadena de conexión al cubo es demasiado larga.")
    if not _CUBE_ADDRESS_PATTERN.match(candidate):
        raise ValueError("Formato de conexión al cubo no permitido.")
    if "password=" in candidate.lower() or "pwd=" in candidate.lower():
        raise ValueError("No se permiten credenciales en la cadena de conexión.")
    if "YOUR_SSAS_HOST" in candidate:
        raise ValueError(
            "cube_address contiene el placeholder YOUR_SSAS_HOST. "
            "Configure DEFAULT_CUBE_ADDRESS en agent_api/.env."
        )

    return candidate


def _resolve_cube_address(cube_address: str, *, use_mock: bool) -> str:
    """Valida la cadena del cubo del servidor."""
    if use_mock:
        return cube_address
    if not cube_address:
        raise ValueError(
            "DEFAULT_CUBE_ADDRESS no está configurada. "
            "Copie agent_api/.env.example a agent_api/.env o active SSAS_USE_MOCK=true."
        )
    if "YOUR_SSAS_HOST" in cube_address:
        raise ValueError(
            "DEFAULT_CUBE_ADDRESS aún tiene el placeholder YOUR_SSAS_HOST. "
            "Edite agent_api/.env con el host SSAS real de su entorno."
        )
    return cube_address


def validate_question(question: str) -> str:
    text = question.strip()
    if not text:
        raise ValueError("La pregunta no puede estar vacía.")
    if len(text) > MAX_QUESTION_LENGTH:
        raise ValueError(f"La pregunta no puede superar {MAX_QUESTION_LENGTH} caracteres.")
    return text


def validate_dax_query(dax_query: str) -> str:
    from agent_api.core.agents.llm_utils import is_valid_dax_structure, sanitize_dax_query

    text = sanitize_dax_query(dax_query)
    if not text:
        raise ValueError(
            "La consulta DAX está vacía o no es válida. "
            "Debe comenzar con EVALUATE seguido de ROW, FILTER, SUMMARIZECOLUMNS, TOPN, etc."
        )
    if len(text) > MAX_DAX_LENGTH:
        raise ValueError(f"La consulta DAX no puede superar {MAX_DAX_LENGTH} caracteres.")
    if not is_valid_dax_structure(text):
        raise ValueError(
            "La consulta DAX no tiene formato ejecutable. "
            "No se permiten instrucciones ni ejemplos del prompt; solo DAX real."
        )
    if _FORBIDDEN_DAX.search(text):
        raise ValueError("La consulta DAX contiene operaciones no permitidas.")
    return text


def truncate_rows(rows: list[dict], limit: int = MAX_RESULT_ROWS) -> list[dict]:
    if len(rows) <= limit:
        return rows
    return rows[:limit]
