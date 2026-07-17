"""Pruebas de sanitización DAX (evitar eco del prompt y prosa mezclada)."""
from __future__ import annotations

from agent_api.core.agents.llm_utils import (
    compact_execution_error,
    is_valid_dax_structure,
    sanitize_dax_query,
)
from agent_api.core.security import validate_dax_query

PROMPT_ECHO = """REGLAS DAX OBLIGATORIAS:
- Las consultas deben comenzar with EVALUATE.
- Para conteos: EVALUATE ROW("Total", COUNTROWS('Tabla'))
- Para agrupaciones: EVALUATE SUMMARIZECOLUMNS('Tabla'[Columna], "Total", COUNTROWS('Tabla'))
FILTROS POR VALORES CATEGÓRICOS (país, región, cliente, etc.):
- PRIMERO llama lookup_dimension_values
"""

VALID = (
    "EVALUATE SUMMARIZECOLUMNS('BI_FlotHs Mod01_Equipo'[Pais_Destino], "
    '"Total", COUNTROWS(\'BI_FlotHs Mod01_Equipo\'))'
)

CONTAMINATED = (
    VALID
    + "\n\nJustificación: esta consulta agrupa por país destino para responder "
    "la pregunta del usuario usando COUNTROWS."
)

WITH_RATIONALE_INLINE = (
    VALID
    + "\nEsta consulta filtra por Estados Unidos y muestra las regiones."
)

PREFIXED = f"dax_query: {VALID}\n\nrationale: ranking por región"

MARKDOWN = f"```dax\n{VALID}\n```\n\nNota: usar este DAX en SSAS."


def main() -> None:
    assert sanitize_dax_query(PROMPT_ECHO) == ""
    assert not is_valid_dax_structure("EVALUATE.\n- Para conteos:")
    assert is_valid_dax_structure(VALID)
    assert sanitize_dax_query(f"```dax\n{VALID}\n```") == VALID
    assert validate_dax_query(VALID) == VALID

    cleaned = sanitize_dax_query(CONTAMINATED)
    assert cleaned == VALID, cleaned
    assert "Justificación" not in cleaned

    cleaned2 = sanitize_dax_query(WITH_RATIONALE_INLINE)
    assert cleaned2 == VALID, cleaned2
    assert "Estados Unidos" not in cleaned2

    cleaned3 = sanitize_dax_query(PREFIXED)
    assert cleaned3 == VALID, cleaned3

    cleaned4 = sanitize_dax_query(MARKDOWN)
    assert cleaned4 == VALID, cleaned4

    noisy_err = (
        "Error al ejecutar DAX: Query (1, 9) The syntax for '.' is incorrect. "
        f"({PROMPT_ECHO})"
    )
    compact = compact_execution_error(noisy_err)
    assert "FILTROS POR VALORES" not in compact
    print("OK — sanitize/validate DAX")


if __name__ == "__main__":
    main()
