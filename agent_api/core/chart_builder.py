"""
Construye echarts_config a partir de raw_data cuando el LLM no lo genera.
"""

from __future__ import annotations

from typing import Any


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
    return False


def _to_number(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value.replace(",", ""))
    return 0.0


def _has_valid_chart(config: dict[str, Any] | None) -> bool:
    if not config or not isinstance(config, dict):
        return False
    series = config.get("series")
    if not series:
        return False
    items = series if isinstance(series, list) else [series]
    for item in items:
        if not isinstance(item, dict):
            continue
        data = item.get("data")
        if data:
            return True
    return False


def build_echarts_from_data(
    raw_data: list[dict[str, Any]],
    title: str = "Resultado de la consulta",
) -> dict[str, Any]:
    """Genera un gráfico ECharts básico según la forma de los datos."""
    if not raw_data:
        return {}

    rows = [dict(row) for row in raw_data if isinstance(row, dict)]
    if not rows:
        return {}

    keys = list(rows[0].keys())
    numeric_cols = [
        k for k in keys if any(_is_numeric(row.get(k)) for row in rows) and not all(row.get(k) is None for row in rows)
    ]
    text_cols = [k for k in keys if k not in numeric_cols]

    # Valor único (COUNT, ROW con una medida)
    if len(rows) == 1 and len(numeric_cols) == 1:
        measure = numeric_cols[0]
        value = _to_number(rows[0][measure])
        label = str(rows[0].get(text_cols[0], measure)) if text_cols else measure
        return {
            "title": {"text": title},
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category", "data": [label]},
            "yAxis": {"type": "value"},
            "series": [{"name": measure, "type": "bar", "data": [value]}],
        }

    # ROW("Etiqueta", valor) u otra fila con texto + número
    if len(rows) == 1 and len(keys) == 2 and numeric_cols and text_cols:
        cat_col, val_col = text_cols[0], numeric_cols[0]
        return {
            "title": {"text": title},
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category", "data": [str(rows[0][cat_col])]},
            "yAxis": {"type": "value"},
            "series": [{"name": val_col, "type": "bar", "data": [_to_number(rows[0][val_col])]}],
        }

    # Tabla categoría + medida(s)
    if text_cols and numeric_cols:
        cat_col = text_cols[0]
        categories = [str(row.get(cat_col, "")) for row in rows]
        horizontal = max((len(c) for c in categories), default=0) > 14 or len(categories) > 8

        series = [
            {
                "name": measure,
                "type": "bar",
                "data": [_to_number(row.get(measure)) for row in rows],
            }
            for measure in numeric_cols
        ]

        if len(categories) <= 4 and len(numeric_cols) == 1:
            return {
                "title": {"text": title, "left": "center", "top": 8},
                "tooltip": {"trigger": "item"},
                "series": [
                    {
                        "name": numeric_cols[0],
                        "type": "pie",
                        "radius": "55%",
                        "data": [
                            {"name": cat, "value": _to_number(row.get(numeric_cols[0]))}
                            for cat, row in zip(categories, rows)
                        ],
                    }
                ],
            }

        if horizontal:
            return {
                "title": {"text": title, "left": "center", "top": 8},
                "tooltip": {"trigger": "axis"},
                "xAxis": {"type": "value"},
                "yAxis": {"type": "category", "data": categories},
                "series": series,
            }

        return {
            "title": {"text": title, "left": "center", "top": 8},
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category", "data": categories},
            "yAxis": {"type": "value"},
            "series": series,
        }

    # Solo columnas numéricas
    if numeric_cols and not text_cols:
        return {
            "title": {"text": title},
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category", "data": numeric_cols},
            "yAxis": {"type": "value"},
            "series": [
                {
                    "name": "Valores",
                    "type": "bar",
                    "data": [_to_number(rows[0].get(col)) for col in numeric_cols],
                }
            ],
        }

    return {}


SUPPORTED_CHART_TYPES = {"bar", "line", "pie"}


def _series_items(config: dict[str, Any]) -> list[dict[str, Any]]:
    series = config.get("series")
    if not series:
        return []
    if isinstance(series, list):
        return [item for item in series if isinstance(item, dict)]
    if isinstance(series, dict):
        return [series]
    return []


def normalize_echarts_config(config: dict[str, Any]) -> dict[str, Any]:
    """Convierte tipos no soportados en el frontend (gauge, etc.) a bar/line/pie."""
    if not config:
        return config

    normalized: list[dict[str, Any]] = []
    fallback_categories: list[str] = []

    for item in _series_items(config):
        chart_type = str(item.get("type", "bar")).lower()
        if chart_type in SUPPORTED_CHART_TYPES:
            normalized.append(item)
            continue

        data = item.get("data") or []
        values: list[float] = []
        categories: list[str] = []

        for idx, point in enumerate(data):
            if isinstance(point, dict):
                categories.append(str(point.get("name") or f"Item {idx + 1}"))
                values.append(_to_number(point.get("value")))
            else:
                categories.append(str(idx + 1))
                values.append(_to_number(point))

        if not values:
            continue

        normalized.append(
            {
                "name": str(item.get("name") or "Valor"),
                "type": "bar",
                "data": values,
            }
        )
        if not fallback_categories:
            fallback_categories = categories

    if not normalized:
        return config

    config = dict(config)
    config["series"] = normalized

    x_axes = config.get("xAxis")
    y_axes = config.get("yAxis")
    has_category_axis = False
    for axis in (x_axes, y_axes) if not isinstance(x_axes, list) else [x_axes, y_axes]:
        if isinstance(axis, dict) and axis.get("type") == "category" and axis.get("data"):
            has_category_axis = True
            break
        if isinstance(axis, list):
            for ax in axis:
                if isinstance(ax, dict) and ax.get("type") == "category" and ax.get("data"):
                    has_category_axis = True
                    break

    if not has_category_axis and fallback_categories:
        config["xAxis"] = {"type": "category", "data": fallback_categories}
        config["yAxis"] = {"type": "value"}

    config["tooltip"] = config.get("tooltip") or {"trigger": "axis"}
    return _apply_legend_layout(config)


def _is_horizontal_bar(config: dict[str, Any]) -> bool:
    y_axes = config.get("yAxis")
    if isinstance(y_axes, dict):
        return y_axes.get("type") == "category"
    if isinstance(y_axes, list):
        return any(isinstance(ax, dict) and ax.get("type") == "category" for ax in y_axes)
    return False


def _legend_series_names(config: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for item in _series_items(config):
        chart_type = str(item.get("type", "bar")).lower()
        if chart_type == "pie":
            data = item.get("data") or []
            for point in data:
                if isinstance(point, dict) and point.get("name"):
                    names.append(str(point["name"]))
            if not names and item.get("name"):
                names.append(str(item["name"]))
        elif item.get("name"):
            names.append(str(item["name"]))
    return names


def _apply_legend_layout(config: dict[str, Any]) -> dict[str, Any]:
    """Coloca la leyenda abajo o a la derecha para no chocar con el título."""
    if not config:
        return config

    config = dict(config)
    series_items = _series_items(config)
    if not series_items:
        return config

    has_pie = any(str(s.get("type", "")).lower() == "pie" for s in series_items)
    multi_series = len(series_items) > 1
    legend_names = _legend_series_names(config)
    needs_legend = has_pie or multi_series or len(legend_names) > 1

    title = config.get("title")
    if isinstance(title, dict):
        config["title"] = {
            **title,
            "left": title.get("left", "center"),
            "top": title.get("top", 8),
            "textStyle": {
                "fontSize": 14,
                "fontWeight": 600,
                **(title.get("textStyle") or {}),
            },
        }
    elif title:
        config["title"] = {"text": str(title), "left": "center", "top": 8}

    grid = dict(config.get("grid") or {})
    grid.setdefault("left", "3%")
    grid.setdefault("right", "4%")
    grid.setdefault("containLabel", True)
    grid.setdefault("top", 52)

    if not needs_legend:
        config["legend"] = {"show": False}
        grid.setdefault("bottom", "8%")
        config["grid"] = grid
        return config

    horizontal = _is_horizontal_bar(config)
    use_right = horizontal and (multi_series or len(legend_names) > 4)

    if use_right:
        config["legend"] = {
            "show": True,
            "type": "scroll",
            "orient": "vertical",
            "right": 8,
            "top": "middle",
            "data": legend_names or None,
            "textStyle": {"fontSize": 11},
        }
        grid["right"] = "16%"
        grid["bottom"] = grid.get("bottom", "10%")
    else:
        config["legend"] = {
            "show": True,
            "type": "scroll",
            "orient": "horizontal",
            "bottom": 8,
            "left": "center",
            "data": legend_names or None,
            "textStyle": {"fontSize": 11},
        }
        existing_bottom = grid.get("bottom", "8%")
        if isinstance(existing_bottom, (int, float)) and existing_bottom < 40:
            grid["bottom"] = 48
        elif existing_bottom in ("3%", "8%", "10%"):
            grid["bottom"] = "14%"

    config["grid"] = grid
    return config


def ensure_echarts_config(
    echarts_config: dict[str, Any] | None,
    raw_data: list[dict[str, Any]],
    title: str = "Resultado de la consulta",
) -> dict[str, Any]:
    """Usa el config del LLM o genera uno desde raw_data."""
    if _has_valid_chart(echarts_config):
        config = echarts_config  # type: ignore[assignment]
    else:
        config = build_echarts_from_data(raw_data, title=title)
    return normalize_echarts_config(config)
