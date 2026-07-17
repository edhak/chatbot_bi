"""
Catálogo y selector inteligente de gráficos ECharts para datos BI.

Analiza la forma de raw_data (filas, columnas, cardinalidad, tiempo, etc.)
y elige el tipo más adecuado entre los soportados por el frontend.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

ChartType = Literal[
    "bar",
    "bar_horizontal",
    "bar_stacked",
    "line",
    "pie",
    "treemap",
    "heatmap",
    "scatter",
    "radar",
    "gauge",
    "funnel",
    "candlestick",
]

SUPPORTED_CHART_TYPES: set[str] = {
    "bar",
    "line",
    "pie",
    "bar_horizontal",
    "bar_stacked",
    "treemap",
    "heatmap",
    "scatter",
    "radar",
    "gauge",
    "funnel",
    "candlestick",
}

# Catálogo de tipos disponibles en el frontend (bar/line/pie)
CHART_CATALOG: dict[str, dict[str, Any]] = {
    "bar": {
        "echarts_type": "bar",
        "label": "Barras verticales",
        "best_for": [
            "Comparar categorías (2–12 ítems)",
            "Rankings y top N moderados",
            "Una o pocas métricas por categoría",
        ],
        "avoid_when": [
            "Muchas categorías (>12) o etiquetas largas",
            "Evolución temporal (preferir línea)",
            "Partes de un todo con pocas categorías (preferir torta)",
        ],
        "data_shape": "1 dimensión categórica + 1+ medidas numéricas",
        "max_categories": 12,
    },
    "bar_horizontal": {
        "echarts_type": "bar",
        "label": "Barras horizontales",
        "best_for": [
            "Muchas categorías (>8)",
            "Etiquetas largas (nombres de equipos, clientes)",
            "Rankings extensos",
        ],
        "avoid_when": [
            "Series temporales ordenadas",
            "Solo 2–4 categorías para composición %",
        ],
        "data_shape": "Igual que barras, eje categoría en Y",
        "max_categories": 40,
    },
    "bar_stacked": {
        "echarts_type": "bar",
        "label": "Barras apiladas",
        "best_for": [
            "Varias métricas sobre las mismas categorías",
            "Composición o desglose por dimensión",
            "Comparar totales y contribución de partes",
        ],
        "avoid_when": [
            "Una sola medida (usar bar simple)",
            "Demasiadas series (>4)",
            "Series temporales (preferir línea múltiple)",
        ],
        "data_shape": "1 categoría + 2–4 medidas numéricas",
        "max_categories": 15,
    },
    "line": {
        "echarts_type": "line",
        "label": "Líneas",
        "best_for": [
            "Tendencias en el tiempo (año, mes, trimestre)",
            "Secuencias ordenadas (periodos consecutivos)",
            "Evolución de una o varias métricas",
        ],
        "avoid_when": [
            "Categorías nominales sin orden (regiones, productos)",
            "Un solo valor (KPI)",
            "Composición % con pocas categorías",
        ],
        "data_shape": "Dimensión temporal/ordenada + 1–3 medidas",
        "max_categories": 36,
    },
    "pie": {
        "echarts_type": "pie",
        "label": "Torta / pastel",
        "best_for": [
            "Parte de un todo (2–6 segmentos)",
            "Distribución porcentual simple",
            "Una sola medida y pocas categorías",
        ],
        "avoid_when": [
            "Más de 6 categorías",
            "Comparar magnitudes entre muchos ítems",
            "Series temporales o múltiples medidas",
        ],
        "data_shape": "1 categoría + 1 medida, 2–6 filas",
        "max_categories": 6,
    },
    "treemap": {
        "echarts_type": "treemap",
        "label": "Treemap / mapa de áreas",
        "best_for": [
            "Distribución proporcional con 7–30 categorías",
            "Ver participación relativa cuando hay muchos segmentos",
            "Composición visual más clara que torta con muchos ítems",
        ],
        "avoid_when": [
            "Menos de 7 categorías (preferir torta o barras)",
            "Series temporales u ordenadas",
            "Múltiples medidas por categoría",
            "Comparar ranking exacto (preferir barras horizontales)",
        ],
        "data_shape": "1 categoría + 1 medida, 7–50 filas",
        "max_categories": 50,
    },
    "heatmap": {
        "echarts_type": "heatmap",
        "label": "Mapa de calor (heatmap)",
        "best_for": [
            "Matriz con 2 dimensiones categóricas + 1 medida",
            "Categoría × varias medidas (intensidad por celda)",
            "Patrones cruzados (país×región, tipo×estado, etc.)",
        ],
        "avoid_when": [
            "Una sola categoría y una sola medida",
            "Series temporales simples (preferir línea)",
            "KPI de valor único",
            "Matrices enormes (>40×40) difíciles de leer",
        ],
        "data_shape": "2 dimensiones + 1 medida, o 1 categoría + 2–8 medidas",
        "max_categories": 40,
    },
    "scatter": {
        "echarts_type": "scatter",
        "label": "Dispersión (scatter)",
        "best_for": [
            "Relación entre dos medidas numéricas",
            "Detectar correlación o outliers",
            "Comparar pares (X vs Y) por categoría",
        ],
        "avoid_when": [
            "Una sola medida",
            "Series temporales simples (preferir línea)",
            "KPI de valor único",
        ],
        "data_shape": "2 medidas numéricas (+ categoría opcional para etiquetas)",
        "max_categories": 200,
    },
    "radar": {
        "echarts_type": "radar",
        "label": "Radar",
        "best_for": [
            "Comparar 3–8 métricas en paralelo",
            "Perfil multidimensional de pocos ítems (2–5)",
            "Balanced scorecard / dimensiones múltiples",
        ],
        "avoid_when": [
            "Una o dos medidas solamente",
            "Muchas categorías (>6)",
            "Serie temporal OHLC",
        ],
        "data_shape": "3–8 medidas × 1–5 categorías",
        "max_categories": 6,
    },
    "gauge": {
        "echarts_type": "gauge",
        "label": "Medidor (gauge)",
        "best_for": [
            "KPI de valor único",
            "Indicador con meta o rango visual",
            "Resumen ejecutivo numérico",
        ],
        "avoid_when": [
            "Varias categorías o filas",
            "Series temporales",
            "Composición por segmentos",
        ],
        "data_shape": "1 fila + 1 medida",
        "max_categories": 1,
    },
    "funnel": {
        "echarts_type": "funnel",
        "label": "Embudo (funnel)",
        "best_for": [
            "Etapas ordenadas de un proceso (3–10)",
            "Conversión o pipeline decreciente",
            "Ranking con foco en proporción secuencial",
        ],
        "avoid_when": [
            "Series temporales",
            "Más de 12 etapas",
            "Múltiples medidas sin agregar",
        ],
        "data_shape": "1 categoría + 1 medida, 3–12 filas",
        "max_categories": 12,
    },
    "candlestick": {
        "echarts_type": "candlestick",
        "label": "Velas (candlestick)",
        "best_for": [
            "Serie temporal con OHLC (apertura, máximo, mínimo, cierre)",
            "Evolución financiera / rangos por periodo",
        ],
        "avoid_when": [
            "Sin columnas OHLC",
            "Categorías nominales sin orden temporal",
            "Un solo valor",
        ],
        "data_shape": "Dimensión temporal + 4 medidas OHLC",
        "max_categories": 120,
    },
}

_FUNNEL_COL_HINTS = (
    "etapa", "fase", "paso", "stage", "funnel", "embudo", "nivel", "step", "pipeline",
    "conversion", "conversión",
)
_DATE_VALUE_RE = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}")

_OHLC_HINTS = {
    "open": "open",
    "apertura": "open",
    "high": "high",
    "maximo": "high",
    "máximo": "high",
    "max": "high",
    "low": "low",
    "minimo": "low",
    "mínimo": "low",
    "min": "low",
    "close": "close",
    "cierre": "close",
}


def _detect_ohlc_columns(columns: list[str]) -> dict[str, str] | None:
    """Mapea columnas numéricas a open/high/low/close si los nombres lo sugieren."""
    mapping: dict[str, str] = {}
    for col in columns:
        key = re.sub(r"[^a-z0-9]", "", col.lower())
        for hint, role in _OHLC_HINTS.items():
            if hint in key and role not in mapping:
                mapping[role] = col
                break
    if all(role in mapping for role in ("open", "high", "low", "close")):
        return mapping
    return None


_TIME_COLUMN_RE = re.compile(
    r"(fecha|año|ano|anio|year|mes|month|trimestre|quarter|periodo|semana|dia|day|time)",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"^\d{4}$")
_QUARTER_RE = re.compile(r"^Q[1-4](\s*\d{2,4})?$", re.IGNORECASE)
_MONTH_NAMES = {
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
}


@dataclass
class DataProfile:
    row_count: int = 0
    numeric_columns: list[str] = field(default_factory=list)
    text_columns: list[str] = field(default_factory=list)
    category_column: str | None = None
    categories: list[str] = field(default_factory=list)
    category_count: int = 0
    secondary_category_column: str | None = None
    secondary_category_count: int = 0
    max_label_length: int = 0
    is_single_value: bool = False
    is_time_series: bool = False
    is_ordered_sequence: bool = False
    has_multiple_measures: bool = False
    all_values_positive: bool = True
    is_funnel_like: bool = False
    has_ohlc: bool = False


@dataclass
class ChartRecommendation:
    chart_type: ChartType
    confidence: float
    reason: str
    alternatives: list[dict[str, Any]] = field(default_factory=list)


def _looks_like_year_value(value: Any) -> bool:
    if isinstance(value, int) and 1900 <= value <= 2100:
        return True
    if isinstance(value, str) and _YEAR_RE.match(value.strip()):
        return True
    return False


def _is_dimension_column(column_name: str, values: list[Any]) -> bool:
    """Detecta columnas categóricas aunque vengan como número (años, códigos)."""
    if _looks_like_time_column(column_name):
        return True

    dim_hints = (
        "pais", "país", "region", "región", "zona", "cliente", "equipo",
        "producto", "categoria", "categoría", "tipo", "estado", "nombre",
        "codigo", "código", "marca", "modelo", "ciudad", "departamento",
    )
    measure_hints = (
        "total", "suma", "cantidad", "monto", "venta", "costo", "precio",
        "horas", "importe", "valor", "promedio", "media", "count", "indice",
        "índice", "porcentaje", "tasa", "numero", "número",
    )
    col_lower = column_name.lower()
    if any(hint in col_lower for hint in measure_hints):
        return False
    if any(hint in col_lower for hint in dim_hints):
        return True

    non_empty = [v for v in values if v is not None and str(v).strip()]
    if not non_empty:
        return False

    if all(_looks_like_year_value(v) for v in non_empty):
        return True

    # Pocos valores únicos respecto a filas → probable dimensión
    unique = {str(v).strip() for v in non_empty}
    if len(unique) <= max(12, len(non_empty)):
        str_values = [str(v).strip() for v in non_empty]
        if not all(_is_numeric(v) for v in non_empty):
            if sum(1 for v in str_values if _looks_ordered_category(v)) >= len(str_values) * 0.5:
                return True

    return False


def _is_measure_column(column_name: str, values: list[Any]) -> bool:
    if _is_dimension_column(column_name, values):
        return False
    return any(_is_numeric(v) for v in values) and not all(v is None for v in values)


def _is_numeric(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value.replace(",", ""))
            return True
        except ValueError:
            return False
    type_name = type(value).__name__
    if type_name in {
        "Int16", "Int32", "Int64", "UInt16", "UInt32", "UInt64",
        "Byte", "SByte", "Single", "Double", "Decimal",
        "SqlInt16", "SqlInt32", "SqlInt64", "SqlByte",
        "SqlDecimal", "SqlSingle", "SqlDouble", "SqlMoney",
    }:
        return True
    try:
        float(value)  # type: ignore[arg-type]
        return True
    except (TypeError, ValueError):
        return False


def _to_number(value: Any) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    try:
        from decimal import Decimal

        if isinstance(value, Decimal):
            return float(value)
    except Exception:
        pass
    if isinstance(value, str):
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return 0.0
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        try:
            return float(str(value).replace(",", ""))
        except ValueError:
            return 0.0


def coerce_rows_for_charts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Normaliza filas para gráficos: convierte medidas CLR/string a int/float nativos.
    Evita que System.Int64 quede como dimensión y el builder devuelva {}.
    """
    if not rows:
        return []
    coerced: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out: dict[str, Any] = {}
        for key, value in row.items():
            if value is None or isinstance(value, bool):
                out[key] = value
            elif isinstance(value, (int, float)):
                out[key] = value
            elif _is_numeric(value):
                num = _to_number(value)
                if num == int(num) and abs(num) < 1e15:
                    out[key] = int(num)
                else:
                    out[key] = num
            else:
                # Intento final por nombre de tipo CLR / representación textual
                type_name = type(value).__name__
                if type_name in {
                    "Int16", "Int32", "Int64", "UInt16", "UInt32", "UInt64",
                    "Byte", "SByte", "Single", "Double", "Decimal",
                }:
                    try:
                        num = float(str(value).strip().replace(",", ""))
                        out[key] = int(num) if num == int(num) else num
                        continue
                    except ValueError:
                        pass
                out[key] = value
        coerced.append(out)
    return coerced


def _looks_like_time_column(column_name: str) -> bool:
    return bool(_TIME_COLUMN_RE.search(column_name))


def _looks_ordered_category(value: str) -> bool:
    text = str(value).strip()
    if not text:
        return False
    if _YEAR_RE.match(text):
        return True
    if _QUARTER_RE.match(text):
        return True
    if _DATE_VALUE_RE.match(text):
        return True
    if text.lower() in _MONTH_NAMES:
        return True
    if re.match(r"^\d{1,2}$", text):
        return True
    return False


def _detect_funnel_semantics(profile: DataProfile) -> bool:
    """Embudo solo si la dimensión sugiere etapas de un proceso."""
    if not profile.category_column or len(profile.numeric_columns) != 1:
        return False
    col_lower = profile.category_column.lower()
    if not any(hint in col_lower for hint in _FUNNEL_COL_HINTS):
        return False
    return 3 <= profile.category_count <= 12


def _ordered_sequence_ratio(categories: list[str]) -> float:
    if not categories:
        return 0.0
    hits = sum(1 for cat in categories if _looks_ordered_category(cat))
    return hits / len(categories)


def profile_data(rows: list[dict[str, Any]]) -> DataProfile:
    """Perfila la forma de los datos para decidir el gráfico."""
    profile = DataProfile()
    if not rows:
        return profile

    clean_rows = [dict(row) for row in rows if isinstance(row, dict)]
    if not clean_rows:
        return profile

    profile.row_count = len(clean_rows)
    keys = list(clean_rows[0].keys())

    measure_cols: list[str] = []
    dimension_cols: list[str] = []
    for key in keys:
        col_values = [row.get(key) for row in clean_rows]
        if _is_measure_column(key, col_values):
            measure_cols.append(key)
        elif not all(v is None for v in col_values):
            dimension_cols.append(key)

    profile.numeric_columns = measure_cols
    profile.text_columns = dimension_cols
    profile.has_multiple_measures = len(profile.numeric_columns) > 1

    if profile.text_columns:
        profile.category_column = profile.text_columns[0]
        profile.categories = [str(row.get(profile.category_column, "")) for row in clean_rows]
        profile.category_count = len(set(profile.categories))
        profile.max_label_length = max((len(c) for c in profile.categories), default=0)

        col_name = profile.category_column
        temporal_ratio = _ordered_sequence_ratio(profile.categories)
        has_time_name = _looks_like_time_column(col_name)
        profile.is_time_series = has_time_name and temporal_ratio >= 0.5
        if not profile.is_time_series:
            profile.is_ordered_sequence = temporal_ratio >= 0.6

        if len(profile.text_columns) >= 2:
            profile.secondary_category_column = profile.text_columns[1]
            secondary = [str(row.get(profile.secondary_category_column, "")) for row in clean_rows]
            profile.secondary_category_count = len(set(secondary))

    profile.is_funnel_like = _detect_funnel_semantics(profile)
    profile.has_ohlc = _detect_ohlc_columns(profile.numeric_columns) is not None

    profile.is_single_value = profile.row_count == 1 and len(profile.numeric_columns) == 1

    if profile.numeric_columns:
        for row in clean_rows:
            for col in profile.numeric_columns:
                val = _to_number(row.get(col))
                if val < 0:
                    profile.all_values_positive = False
                    break
            if not profile.all_values_positive:
                break

    return profile


def _score_chart_type(chart_type: ChartType, profile: DataProfile) -> tuple[float, str]:
    """Puntúa qué tan adecuado es un tipo de gráfico para el perfil de datos."""
    has_categories = bool(profile.text_columns)
    n_cat = profile.category_count if has_categories else 0
    n_measures = len(profile.numeric_columns)
    long_labels = profile.max_label_length > 14

    if profile.is_single_value:
        if chart_type == "gauge":
            return 0.98, "KPI de valor único; medidor."
        if chart_type == "bar":
            return 0.85, "Valor único (KPI); barra simple."
        return 0.2, "Un solo valor; otros tipos aportan poco."

    if chart_type == "gauge":
        return 0.05, "Gauge solo para KPI de valor único."

    if chart_type == "scatter":
        if n_measures == 2 and not profile.is_single_value:
            if not has_categories:
                if profile.is_time_series:
                    return 0.72, "Dos medidas en el tiempo; scatter posible."
                return 0.88, "Correlación entre 2 medidas numéricas."
            if not profile.is_time_series:
                return 0.52, "Dos medidas por categoría; barras apiladas suelen ser más claras."
            return 0.55, "Scatter con dimensión temporal."
        if n_measures > 2:
            return 0.2, "Scatter requiere 2 medidas; preferir radar."
        return 0.1, "Scatter requiere al menos 2 medidas."

    if chart_type == "radar":
        if 3 <= n_measures <= 8 and 1 <= n_cat <= 6:
            if n_cat == 1:
                return 0.96, f"Perfil radar con {n_measures} métricas."
            return 0.9, f"Comparación radar: {n_measures} métricas × {n_cat} ítems."
        if n_measures >= 3 and n_cat == 0:
            return 0.55, "Solo medidas; radar limitado."
        return 0.15, "Radar necesita 3–8 medidas."

    if chart_type == "funnel":
        if n_measures != 1:
            return 0.0, "Embudo requiere una sola medida."
        if profile.is_time_series:
            return 0.15, "No usar embudo en series temporales."
        if not profile.is_funnel_like:
            return 0.12, "Sin semántica de embudo (columna de etapas)."
        if 3 <= n_cat <= 12 and profile.all_values_positive:
            return 0.93, f"Embudo con {n_cat} etapas de proceso."
        return 0.25, "Pocas o demasiadas etapas para embudo."

    if chart_type == "candlestick":
        if profile.has_ohlc and (profile.is_time_series or profile.is_ordered_sequence) and n_cat >= 3:
            return 0.97, "Serie temporal con columnas OHLC detectadas."
        if profile.has_ohlc:
            return 0.6, "OHLC detectado sin serie temporal clara."
        return 0.05, "Sin columnas OHLC (open/high/low/close)."

    if chart_type == "pie":
        if n_measures != 1:
            return 0.0, "Torta requiere una sola medida."
        if profile.is_funnel_like:
            return 0.35, "Datos de embudo; pie no es ideal."
        if profile.secondary_category_count >= 2:
            return 0.15, "Hay 2 dimensiones categóricas; preferir heatmap."
        if profile.is_time_series or profile.is_ordered_sequence:
            return 0.1, "No usar torta en series temporales u ordenadas."
        if 2 <= n_cat <= 6 and profile.all_values_positive:
            score = 0.95 if n_cat <= 4 else 0.75
            return score, f"Composición con {n_cat} categorías."
        if n_cat > 6:
            return 0.15, "Demasiadas categorías para torta."
        return 0.4, "Pocas categorías pero no ideal para composición."

    if chart_type == "treemap":
        if n_measures != 1:
            return 0.0, "Treemap requiere una sola medida."
        if profile.secondary_category_count >= 2:
            return 0.2, "Hay 2 dimensiones; preferir heatmap."
        if profile.is_time_series or profile.is_ordered_sequence:
            return 0.1, "No usar treemap en series temporales u ordenadas."
        if long_labels:
            return 0.3, "Etiquetas largas; ranking horizontal es más legible."
        if 12 <= n_cat <= 30 and profile.all_values_positive:
            return 0.88, f"Distribución proporcional con {n_cat} categorías."
        if 31 <= n_cat <= 50:
            return 0.85, f"Muchas categorías ({n_cat}); treemap compacto."
        if 7 <= n_cat <= 11 and profile.all_values_positive:
            return 0.68, f"Composición con {n_cat} categorías (barras también válidas)."
        if 2 <= n_cat <= 6:
            return 0.45, "Pocas categorías; torta o barras son más claras."
        return 0.2, "Rango de categorías no ideal para treemap."

    if chart_type == "heatmap":
        n_text = len(profile.text_columns)
        n_sec = profile.secondary_category_count
        if profile.is_single_value:
            return 0.0, "KPI de un solo valor; heatmap no aplica."
        if n_text >= 2 and n_measures == 1:
            if 2 <= n_cat <= 40 and 2 <= n_sec <= 40:
                cells = n_cat * n_sec
                if cells <= 400:
                    return 0.96, (
                        f"Matriz {n_cat}×{n_sec} "
                        f"({profile.category_column} × {profile.secondary_category_column})."
                    )
                return 0.35, "Matriz demasiado grande para heatmap legible."
            return 0.4, "Dos dimensiones presentes pero cardinalidad poco útil."
        if n_text >= 1 and n_measures >= 2:
            if 3 <= n_cat <= 25 and 2 <= n_measures <= 8:
                return 0.86, f"Matriz categoría × {n_measures} medidas."
            if n_measures > 8:
                return 0.25, "Demasiadas medidas para heatmap."
            return 0.35, "Varias medidas; barras apiladas pueden ser más claras."
        return 0.05, "Heatmap necesita 2 dimensiones o varias medidas."

    if chart_type == "line":
        if profile.has_ohlc and profile.is_time_series:
            return 0.68, "Serie temporal OHLC; velas serían más informativas."
        if profile.is_time_series:
            score = 0.95 if n_cat >= 3 else 0.7
            return score, f"Dimensión temporal detectada ({profile.category_column})."
        if profile.is_ordered_sequence and n_cat >= 3:
            return 0.85, "Secuencia ordenada (meses, años, periodos)."
        if n_measures >= 2 and (profile.is_time_series or profile.is_ordered_sequence):
            return 0.9, "Varias métricas en el tiempo."
        if not profile.is_time_series and not profile.is_ordered_sequence:
            return 0.25, "Categorías nominales sin orden temporal."
        return 0.5, "Línea posible pero no óptima."

    if chart_type == "bar_stacked":
        if n_measures < 2:
            return 0.1, "Apilado requiere al menos 2 medidas."
        if not has_categories:
            return 0.18, "Apilado requiere dimensión categórica."
        if 2 <= n_measures <= 4 and not profile.is_time_series:
            if 2 <= n_cat <= 15:
                return 0.91, f"{n_measures} medidas para apilar por categoría."
            return 0.5, "Muchas categorías para apilado."
        if profile.is_time_series:
            return 0.35, "Varias medidas en tiempo; preferir líneas."
        return 0.2, "No hay múltiples medidas para apilar."

    if chart_type == "bar_horizontal":
        if n_measures != 1:
            return 0.12, "Barras horizontales para una medida por categoría."
        if profile.is_time_series or profile.is_ordered_sequence:
            return 0.2, "Series ordenadas se leen mejor en línea o barra vertical."
        if long_labels and n_cat >= 7:
            return 0.94, f"Ranking con etiquetas largas ({n_cat} ítems)."
        if 12 <= n_cat <= 30:
            return 0.87, f"Ranking extenso con {n_cat} categorías."
        if n_cat > 30:
            return 0.93, f"Ranking muy extenso ({n_cat} ítems)."
        if 9 <= n_cat <= 11:
            return 0.82, f"Ranking con {n_cat} categorías."
        return 0.45, "Pocas categorías; barra vertical suele bastar."

    if chart_type == "bar":
        if not has_categories and n_measures >= 2:
            return 0.15, "Sin dimensión categórica; scatter o radar según medidas."
        if profile.is_time_series and n_cat >= 4:
            return 0.55, "Temporal con barra vertical (línea sería mejor)."
        if profile.is_ordered_sequence:
            return 0.5, "Secuencia ordenada; línea podría ser mejor."
        if n_cat > 12 or long_labels:
            return 0.3, "Demasiadas categorías para barras verticales."
        if 2 <= n_cat <= 12 and n_measures >= 1:
            return 0.8, f"Comparación de {n_cat} categorías."
        if n_cat <= 4 and n_measures == 1 and not profile.is_time_series:
            return 0.6, "Pocas categorías; torta también es válida."
        return 0.65, "Comparación categórica estándar."

    return 0.0, "Tipo no evaluado."


def score_chart_type(chart_type: ChartType, rows: list[dict[str, Any]]) -> tuple[float, str]:
    """Puntúa un tipo de gráfico para un conjunto de filas (API pública para validación)."""
    return _score_chart_type(chart_type, profile_data(rows))


def recommend_chart_type(rows: list[dict[str, Any]]) -> ChartRecommendation:
    """
    Recomienda el mejor tipo de gráfico ECharts según los datos.
    Usa el catálogo CHART_CATALOG y reglas de puntuación (sin LLM).
    """
    profile = profile_data(rows)
    if not profile.numeric_columns:
        return ChartRecommendation(
            chart_type="bar",
            confidence=0.0,
            reason="Sin columnas numéricas; no hay gráfico adecuado.",
        )

    scores: list[tuple[ChartType, float, str]] = []
    for chart_type in (
        "line",
        "candlestick",
        "heatmap",
        "gauge",
        "treemap",
        "pie",
        "funnel",
        "radar",
        "scatter",
        "bar_stacked",
        "bar_horizontal",
        "bar",
    ):
        score, reason = _score_chart_type(chart_type, profile)
        if score > 0:
            scores.append((chart_type, score, reason))

    scores.sort(key=lambda item: item[1], reverse=True)
    if not scores:
        return ChartRecommendation(
            chart_type="bar",
            confidence=0.5,
            reason="Fallback: barras verticales.",
        )

    best_type, best_score, best_reason = scores[0]
    alternatives = [
        {
            "type": chart_type,
            "score": round(score, 2),
            "label": CHART_CATALOG[chart_type]["label"],
            "reason": reason,
        }
        for chart_type, score, reason in scores[1:4]
    ]

    return ChartRecommendation(
        chart_type=best_type,
        confidence=round(best_score, 2),
        reason=best_reason,
        alternatives=alternatives,
    )


def get_chart_catalog_for_prompt() -> str:
    """Resumen del catálogo para documentación o prompts (opcional)."""
    lines = ["CATÁLOGO DE GRÁFICOS ECHARTS DISPONIBLES:"]
    for key, meta in CHART_CATALOG.items():
        lines.append(f"  - {key} ({meta['label']}): {meta['data_shape']}")
        lines.append(f"    Ideal para: {'; '.join(meta['best_for'][:2])}")
    return "\n".join(lines)
