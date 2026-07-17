"""
llm_utils — helpers compartidos (evita circular imports con __init__).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from langchain_openai import ChatOpenAI

from agent_api.core.debug_log import AgentDebugTrace
from agent_api.core.state import AgentState

_LLM_CACHE: dict[tuple[float, int], ChatOpenAI] = {}


def get_llm(*, temperature: float = 0.1, max_tokens: int = 1000) -> ChatOpenAI:
    """Devuelve un cliente LLM. Cachea por (temperature, max_tokens) para respetar límites."""
    key = (float(temperature), int(max_tokens))
    cached = _LLM_CACHE.get(key)
    if cached is not None:
        return cached

    client = ChatOpenAI(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=temperature,
        timeout=int(os.getenv("LLM_TIMEOUT_SEC", "60")),
        max_tokens=max_tokens,
    )
    _LLM_CACHE[key] = client
    return client


def get_trace(state: AgentState) -> AgentDebugTrace:
    trace = state.get("_trace")
    if trace is None:
        return AgentDebugTrace()
    return trace


def message_content_to_str(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text") or block.get("content") or block))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content)


_DAX_BODY_START = re.compile(
    r"^EVALUATE\s+(?:"
    r"ROW\s*\("
    r"|FILTER\s*\("
    r"|SUMMARIZECOLUMNS\s*\("
    r"|TOPN\s*\("
    r"|ADDCOLUMNS\s*\("
    r"|SELECTCOLUMNS\s*\("
    r"|CALCULATETABLE\s*\("
    r"|DISTINCT\s*\("
    r"|VALUES\s*\("
    r"|GENERATE\s*\("
    r"|NATURALLEFTOUTERJOIN\s*\("
    r"|CROSSJOIN\s*\("
    r"|UNION\s*\("
    r"|DATATABLE\s*\("
    r"|'\s*[^']+'\s*\["
    r"|\w+\s*\["
    r"|\{"
    r")",
    re.IGNORECASE | re.DOTALL,
)

_PROMPT_BULLET_RE = re.compile(
    r"^-\s+(?:Para|Si|PRIMERO|Usa|NO|Las consultas|Columnas|Tablas|FILTROS|Conteos|"
    r"Agrupaciones|Top N|Filtros)\b",
    re.MULTILINE | re.IGNORECASE,
)

_CONTAMINATION_RE = re.compile(
    r"(?:"
    r"FILTROS POR VALORES"
    r"|lookup_dimension_values"
    r"|REGLAS DAX"
    r"|Herramientas disponibles"
    r"|FASE FINAL"
    r"|dax_query\s*:"
    r"|rationale\s*:"
    r"|Justificaci[oó]n\s*:"
    r"|Explicaci[oó]n\s*:"
    r"|La consulta DAX"
    r"|No uses markdown"
    r"|Sin markdown"
    r"|otro nodo del pipeline"
    r"|PRIMERO llama"
    r")",
    re.IGNORECASE,
)

_TRAILING_PROSE_LINE_RE = re.compile(
    r"^(?:"
    r"nota\b|note\b|explicaci[oó]n\b|justificaci[oó]n\b|rationale\b|"
    r"aqu[ií]\b|this query\b|la consulta\b|esta consulta\b|"
    r"resultado\b|respuesta\b|detalle\b|sugerencia\b|"
    r"usa\b|usar\b|debe\b|deben\b|puede\b|"
    r"\*\*|#{1,3}\s"
    r")",
    re.IGNORECASE,
)


def _balanced_dax_end(text: str) -> int:
    """
    Devuelve el índice final (exclusivo) del EVALUATE con paréntesis balanceados.
    Corta prosa que el LLM añade después del cierre de la expresión.
    """
    if not text.upper().startswith("EVALUATE"):
        return len(text)

    # Buscar el primer '(' tras EVALUATE; si no hay, devolver hasta fin de primera línea útil
    start_paren = text.find("(")
    if start_paren < 0:
        # EVALUATE Tabla[Col] u otra forma sin paréntesis → primera línea
        first_nl = text.find("\n")
        return len(text) if first_nl < 0 else first_nl

    depth = 0
    in_single = False
    in_double = False
    i = start_paren
    while i < len(text):
        ch = text[i]
        prev = text[i - 1] if i > 0 else ""

        if ch == "'" and not in_double and prev != "\\":
            # En DAX las comillas simples de tablas se escapan duplicando ''
            if in_single and i + 1 < len(text) and text[i + 1] == "'":
                i += 2
                continue
            in_single = not in_single
        elif ch == '"' and not in_single and prev != "\\":
            in_double = not in_double
        elif not in_single and not in_double:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return i + 1
        i += 1

    return len(text)


def is_valid_dax_structure(text: str) -> bool:
    """True si el texto parece una consulta DAX ejecutable, no documentación del prompt."""
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    if not _DAX_BODY_START.match(cleaned):
        return False
    if _PROMPT_BULLET_RE.search(cleaned):
        return False
    if _CONTAMINATION_RE.search(cleaned):
        return False
    if re.match(r"^EVALUATE\s*[\.\-]", cleaned, re.IGNORECASE):
        return False
    # Debe tener al menos un paréntesis de función o referencia de columna
    if "(" not in cleaned and "[" not in cleaned:
        return False
    # No permitir párrafos en español largos mezclados
    for line in cleaned.splitlines()[1:]:
        stripped = line.strip()
        if not stripped:
            continue
        if _looks_like_trailing_prose(stripped):
            return False
    return True


def _is_documentation_evaluate(text: str, start: int) -> bool:
    """True si EVALUATE pertenece a una línea de instrucciones, no a consulta real."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", start)
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end]
    stripped = line.strip()
    if stripped.startswith("- "):
        return True
    # Prefijos tipo "Consulta:" / "DAX:" antes de EVALUATE en la misma línea
    prefix = text[line_start:start].strip().lower()
    if prefix and prefix not in {"", "dax", "query"}:
        if any(tok in prefix for tok in ("para ", "ejemplo", "conteo", "agrup", "filtro", ":")):
            return True
    lower = line.lower()
    doc_markers = (
        "deben comenzar",
        "para conteos",
        "para agrupaciones",
        "para top",
        "para filtros",
        "ejemplo:",
        "ejemplos:",
        "reglas dax",
        "como sigue",
    )
    return any(marker in lower for marker in doc_markers)


def _looks_like_trailing_prose(line: str) -> bool:
    """Heurística: líneas posteriores al DAX que son explicación, no código."""
    if line.startswith("```"):
        return True
    if line.startswith("- "):
        return True
    if _TRAILING_PROSE_LINE_RE.match(line):
        return True
    if _CONTAMINATION_RE.search(line):
        return True
    lower = line.lower()
    # Línea en prosa sin tokens DAX típicos
    dax_tokens = (
        "evaluate",
        "summarize",
        "summarizecolumns",
        "filter",
        "topn",
        "row(",
        "calculate",
        "treatas",
        "addcolumns",
        "selectcolumns",
        "countrows",
        "distinctcount",
        "order by",
        "[",
        "]",
        "(",
        ")",
        ",",
        "=",
        "'",
        '"',
    )
    if not any(tok in lower for tok in dax_tokens) and " " in line and len(line) > 25:
        return True
    # Frases típicas en español aunque tengan alguna coma
    spanish_hits = (
        " por ", " del ", " de la ", " de los ", " para ", " con ",
        " que ", " esta ", " este ", " usando ", " genera ",
    )
    if sum(1 for h in spanish_hits if h in lower) >= 2 and "countrows" not in lower:
        if "[" not in line and "evaluate" not in lower:
            return True
    return False


def _trim_dax_tail(text: str) -> str:
    # Primero cortar por balance de paréntesis (elimina rationale pegado al final)
    end = _balanced_dax_end(text)
    text = text[:end].rstrip()

    lines = text.splitlines()
    kept: list[str] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if i > 0 and stripped and _looks_like_trailing_prose(stripped):
            break
        kept.append(line.rstrip())
    result = "\n".join(kept).strip()
    result = re.sub(r"[\s`]+$", "", result).strip()
    # Quitar etiquetas finales tipo // comentario
    result = re.sub(r"\n//.*$", "", result)
    return result


def sanitize_dax_query(text: str) -> str:
    """
    Limpia ruido típico del LLM (markdown, fences, prosa, rationale) y deja solo el DAX.
    Ignora menciones a EVALUATE dentro de instrucciones del prompt.
    Idempotente: seguro llamarla varias veces.
    """
    if not text:
        return ""

    cleaned = str(text).strip()

    # Si viene como JSON {"dax_query": "..."}
    if cleaned.startswith("{") and "dax_query" in cleaned:
        try:
            payload = json.loads(cleaned)
            if isinstance(payload, dict) and payload.get("dax_query"):
                cleaned = str(payload["dax_query"]).strip()
        except Exception:
            pass

    # Prefijos frecuentes del LLM
    cleaned = re.sub(
        r"^(?:dax_query|consulta(?:\s+dax)?|query|dax)\s*[:=]\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()

    # Quitar fences de bloque markdown (inicio/fin o sueltos)
    cleaned = re.sub(r"^```(?:dax|sql|md)?\s*\n?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    cleaned = cleaned.replace("```", "")
    cleaned = cleaned.strip()

    # Probar cada ocurrencia de EVALUATE y quedarse con la primera consulta válida
    for match in re.finditer(r"\bEVALUATE\b", cleaned, re.IGNORECASE):
        if _is_documentation_evaluate(cleaned, match.start()):
            continue
        candidate = _trim_dax_tail(cleaned[match.start() :].strip())
        candidate = re.sub(r"[`'\u2018\u2019\u201c\u201d]+$", "", candidate).strip()
        # Segunda pasada de corte por contaminación residual
        if _CONTAMINATION_RE.search(candidate):
            # Cortar desde el primer marcador de contaminación
            contam = _CONTAMINATION_RE.search(candidate)
            if contam and contam.start() > 10:
                candidate = _trim_dax_tail(candidate[: contam.start()].rstrip())
        if is_valid_dax_structure(candidate):
            return candidate

    return ""


def extract_dax_from_text(text: str) -> str:
    """Alias histórico: sanitiza y extrae DAX desde texto libre del LLM."""
    return sanitize_dax_query(text)

def rows_from_execution_result(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not result or not isinstance(result, dict):
        return []
    if not result.get("ok"):
        return []
    rows = result.get("rows")
    if isinstance(rows, list):
        return [r for r in rows if isinstance(r, dict)]
    return []


def execution_error(result: dict[str, Any] | None) -> str:
    if not result or not isinstance(result, dict):
        return "Sin resultado de ejecución."
    if result.get("ok"):
        return ""
    return compact_execution_error(str(result.get("error") or "Error desconocido al ejecutar DAX."))


def compact_execution_error(error: str, max_len: int = 480) -> str:
    """Resume errores de SSAS sin reinyectar DAX basura en el prompt de retry."""
    text = (error or "").strip()
    if not text:
        return "Error desconocido al ejecutar DAX."
    if len(text) <= max_len and "FILTROS POR VALORES" not in text:
        return text
    # Errores de SSAS suelen incluir la consulta completa entre paréntesis
    if "Error al ejecutar DAX:" in text:
        head = text.split("(", 1)[0].strip()
        return head[:max_len] if head else text[:max_len]
    if "FILTROS POR VALORES" in text or "Para conteos:" in text:
        return (
            "Error al ejecutar DAX: la consulta generada no es válida "
            "(se detectó texto de instrucciones en lugar de DAX real). "
            "Genere EVALUATE seguido de ROW, FILTER, SUMMARIZECOLUMNS o TOPN."
        )
    return text[:max_len] + ("…" if len(text) > max_len else "")


def summarize_rows_compact(rows: list[dict[str, Any]], max_rows: int = 8) -> str:
    if not rows:
        return "Sin filas."
    sample = rows[:max_rows]
    payload: dict[str, Any] = {"total_filas": len(rows), "muestra": sample}
    if len(rows) > max_rows:
        payload["nota"] = f"Mostrando {max_rows} de {len(rows)} filas."
    return json.dumps(payload, ensure_ascii=False, default=str)
