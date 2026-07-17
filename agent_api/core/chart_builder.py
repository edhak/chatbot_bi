"""
Construye echarts_config a partir de raw_data cuando el LLM no lo genera.
Delega la elección del tipo de gráfico a chart_selector (catálogo + reglas).
"""

from __future__ import annotations

from typing import Any

from agent_api.core.chart_selector import (
    CHART_CATALOG,
    ChartRecommendation,
    _detect_ohlc_columns,
    _to_number,
    coerce_rows_for_charts,
    profile_data,
    recommend_chart_type,
)

ECHARTS_SERIES_TYPES = {
    "bar",
    "line",
    "pie",
    "treemap",
    "heatmap",
    "scatter",
    "radar",
    "gauge",
    "funnel",
    "candlestick",
}

_HEATMAP_COLORS = ["#E8F4F8", "#A8D5E5", "#4FA8C7", "#0496CD", "#036B92"]


def _build_treemap_data(
    rows: list[dict[str, Any]],
    category_col: str,
    measure_col: str,
) -> list[dict[str, Any]]:
    return [
        {
            "name": str(row.get(category_col, "")),
            "value": _to_number(row.get(measure_col)),
        }
        for row in rows
    ]


def _build_treemap_config(
    rows: list[dict[str, Any]],
    category_col: str,
    measure_col: str,
    title: str,
    chart_meta: dict[str, Any],
) -> dict[str, Any]:
    return {
        "title": {"text": title, "left": "center", "top": 8},
        "tooltip": {
            "trigger": "item",
            "formatter": "{b}: {c}",
        },
        "series": [
            {
                "name": measure_col,
                "type": "treemap",
                "roam": False,
                "nodeClick": False,
                "breadcrumb": {"show": False},
                "left": "2%",
                "right": "2%",
                "top": 48,
                "bottom": 12,
                "label": {
                    "show": True,
                    "formatter": "{b}",
                    "fontSize": 11,
                },
                "upperLabel": {"show": False},
                "itemStyle": {
                    "borderColor": "#FFFFFF",
                    "borderWidth": 2,
                    "gapWidth": 2,
                },
                "data": _build_treemap_data(rows, category_col, measure_col),
            }
        ],
        "chart_meta": chart_meta,
    }


def _unique_preserve(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _build_heatmap_config(
    *,
    x_labels: list[str],
    y_labels: list[str],
    cells: list[list[float | int]],
    measure_name: str,
    title: str,
    chart_meta: dict[str, Any],
) -> dict[str, Any]:
    values = [float(cell[2]) for cell in cells]
    vmin = min(values) if values else 0.0
    vmax = max(values) if values else 1.0
    if vmax <= vmin:
        vmax = vmin + 1.0

    show_labels = len(cells) <= 100 and len(x_labels) * len(y_labels) <= 120

    return {
        "title": {"text": title, "left": "center", "top": 8},
        "tooltip": {"position": "top"},
        "grid": {
            "left": "3%",
            "right": "4%",
            "top": 56,
            "bottom": 72,
            "containLabel": True,
        },
        "xAxis": {
            "type": "category",
            "data": x_labels,
            "splitArea": {"show": True},
            "axisLabel": {"rotate": 30 if len(x_labels) > 8 else 0},
        },
        "yAxis": {
            "type": "category",
            "data": y_labels,
            "splitArea": {"show": True},
        },
        "visualMap": {
            "min": vmin,
            "max": vmax,
            "calculable": True,
            "orient": "horizontal",
            "left": "center",
            "bottom": 8,
            "text": ["Alto", "Bajo"],
            "inRange": {"color": list(_HEATMAP_COLORS)},
        },
        "legend": {"show": False},
        "series": [
            {
                "name": measure_name,
                "type": "heatmap",
                "data": cells,
                "label": {
                    "show": show_labels,
                    "fontSize": 10,
                },
                "emphasis": {
                    "itemStyle": {
                        "shadowBlur": 8,
                        "shadowColor": "rgba(0, 0, 0, 0.25)",
                    }
                },
            }
        ],
        "chart_meta": chart_meta,
    }


def _heatmap_from_two_dimensions(
    rows: list[dict[str, Any]],
    x_col: str,
    y_col: str,
    measure_col: str,
    title: str,
    chart_meta: dict[str, Any],
) -> dict[str, Any]:
    x_labels = _unique_preserve([str(row.get(x_col, "")) for row in rows])
    y_labels = _unique_preserve([str(row.get(y_col, "")) for row in rows])
    x_index = {label: idx for idx, label in enumerate(x_labels)}
    y_index = {label: idx for idx, label in enumerate(y_labels)}

    aggregated: dict[tuple[int, int], float] = {}
    for row in rows:
        xi = x_index.get(str(row.get(x_col, "")))
        yi = y_index.get(str(row.get(y_col, "")))
        if xi is None or yi is None:
            continue
        aggregated[(xi, yi)] = aggregated.get((xi, yi), 0.0) + _to_number(row.get(measure_col))

    cells: list[list[float | int]] = [
        [xi, yi, value] for (xi, yi), value in aggregated.items()
    ]
    return _build_heatmap_config(
        x_labels=x_labels,
        y_labels=y_labels,
        cells=cells,
        measure_name=measure_col,
        title=title,
        chart_meta=chart_meta,
    )


def _heatmap_from_category_measures(
    rows: list[dict[str, Any]],
    category_col: str,
    measure_cols: list[str],
    title: str,
    chart_meta: dict[str, Any],
) -> dict[str, Any]:
    x_labels = _unique_preserve([str(row.get(category_col, "")) for row in rows])
    y_labels = list(measure_cols)
    x_index = {label: idx for idx, label in enumerate(x_labels)}

    aggregated: dict[tuple[int, int], float] = {}
    for row in rows:
        xi = x_index.get(str(row.get(category_col, "")))
        if xi is None:
            continue
        for yi, measure in enumerate(measure_cols):
            aggregated[(xi, yi)] = aggregated.get((xi, yi), 0.0) + _to_number(row.get(measure))

    cells: list[list[float | int]] = [
        [xi, yi, value] for (xi, yi), value in aggregated.items()
    ]
    return _build_heatmap_config(
        x_labels=x_labels,
        y_labels=y_labels,
        cells=cells,
        measure_name="Valor",
        title=title,
        chart_meta=chart_meta,
    )


def _build_gauge_config(
    value: float,
    measure_name: str,
    title: str,
    chart_meta: dict[str, Any],
) -> dict[str, Any]:
    vmax = max(value * 1.25, value + 1.0, 10.0)
    return {
        "title": {"text": title, "left": "center", "top": 8},
        "tooltip": {"formatter": "{b}: {c}"},
        "series": [
            {
                "name": measure_name,
                "type": "gauge",
                "min": 0,
                "max": vmax,
                "progress": {"show": True, "width": 14},
                "axisLine": {"lineStyle": {"width": 14}},
                "detail": {"valueAnimation": True, "formatter": "{value}", "fontSize": 22},
                "data": [{"value": value, "name": measure_name}],
            }
        ],
        "chart_meta": chart_meta,
    }


def _build_scatter_config(
    rows: list[dict[str, Any]],
    x_col: str,
    y_col: str,
    label_col: str | None,
    title: str,
    chart_meta: dict[str, Any],
) -> dict[str, Any]:
    data: list[Any] = []
    for row in rows:
        x_val = _to_number(row.get(x_col))
        y_val = _to_number(row.get(y_col))
        if label_col:
            data.append({"value": [x_val, y_val], "name": str(row.get(label_col, ""))})
        else:
            data.append([x_val, y_val])

    return {
        "title": {"text": title, "left": "center", "top": 8},
        "tooltip": {"trigger": "item"},
        "grid": {"left": "8%", "right": "6%", "top": 56, "bottom": "12%", "containLabel": True},
        "xAxis": {"type": "value", "name": x_col, "scale": True},
        "yAxis": {"type": "value", "name": y_col, "scale": True},
        "series": [
            {
                "name": f"{y_col} vs {x_col}",
                "type": "scatter",
                "symbolSize": 10,
                "data": data,
            }
        ],
        "chart_meta": chart_meta,
    }


def _build_radar_config(
    rows: list[dict[str, Any]],
    category_col: str | None,
    measure_cols: list[str],
    title: str,
    chart_meta: dict[str, Any],
) -> dict[str, Any]:
    indicators = [{"name": col, "max": 0.0} for col in measure_cols]
    for col in measure_cols:
        max_val = max(_to_number(row.get(col)) for row in rows) if rows else 1.0
        for ind in indicators:
            if ind["name"] == col:
                ind["max"] = max(max_val * 1.15, 1.0)

    series_data: list[dict[str, Any]] = []
    for idx, row in enumerate(rows[:6]):
        name = str(row.get(category_col, f"Serie {idx + 1}")) if category_col else f"Serie {idx + 1}"
        series_data.append(
            {
                "name": name,
                "value": [_to_number(row.get(col)) for col in measure_cols],
            }
        )

    return {
        "title": {"text": title, "left": "center", "top": 8},
        "tooltip": {"trigger": "item"},
        "legend": {"show": len(series_data) > 1, "bottom": 8, "type": "scroll"},
        "radar": {
            "indicator": indicators,
            "radius": "62%",
            "center": ["50%", "55%"],
        },
        "series": [
            {
                "type": "radar",
                "data": series_data,
            }
        ],
        "chart_meta": chart_meta,
    }


def _build_funnel_config(
    rows: list[dict[str, Any]],
    category_col: str,
    measure_col: str,
    title: str,
    chart_meta: dict[str, Any],
) -> dict[str, Any]:
    items = [
        {"name": str(row.get(category_col, "")), "value": _to_number(row.get(measure_col))}
        for row in rows
    ]
    items.sort(key=lambda item: item["value"], reverse=True)

    return {
        "title": {"text": title, "left": "center", "top": 8},
        "tooltip": {"trigger": "item", "formatter": "{b}: {c}"},
        "series": [
            {
                "name": measure_col,
                "type": "funnel",
                "left": "10%",
                "top": 48,
                "bottom": 12,
                "width": "80%",
                "sort": "descending",
                "gap": 2,
                "label": {"show": True, "position": "inside"},
                "data": items,
            }
        ],
        "chart_meta": chart_meta,
    }


def _build_candlestick_config(
    rows: list[dict[str, Any]],
    category_col: str,
    ohlc: dict[str, str],
    title: str,
    chart_meta: dict[str, Any],
) -> dict[str, Any]:
    categories = [str(row.get(category_col, "")) for row in rows]
    candle_data = [
        [
            _to_number(row.get(ohlc["open"])),
            _to_number(row.get(ohlc["close"])),
            _to_number(row.get(ohlc["low"])),
            _to_number(row.get(ohlc["high"])),
        ]
        for row in rows
    ]

    return {
        "title": {"text": title, "left": "center", "top": 8},
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "cross"}},
        "grid": {"left": "6%", "right": "4%", "top": 56, "bottom": "14%", "containLabel": True},
        "xAxis": {"type": "category", "data": categories, "boundaryGap": True},
        "yAxis": {"type": "value", "scale": True},
        "series": [
            {
                "name": "OHLC",
                "type": "candlestick",
                "data": candle_data,
            }
        ],
        "chart_meta": chart_meta,
    }


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
        # gauge puede usar detail sin data explícita en algunos casos
        if str(item.get("type", "")).lower() == "gauge" and item.get("detail"):
            return True
    return False


def has_valid_chart(config: dict[str, Any] | None) -> bool:
    """True si echarts_config tiene series con datos."""
    return _has_valid_chart(config)


def _build_series_data(
    rows: list[dict[str, Any]],
    numeric_cols: list[str],
    chart_type: str,
) -> list[dict[str, Any]]:
    stack_group = "total" if chart_type == "bar_stacked" else None
    echarts_type = CHART_CATALOG.get(chart_type, {}).get("echarts_type", "bar")
    if chart_type == "line":
        echarts_type = "line"

    series: list[dict[str, Any]] = []
    for measure in numeric_cols:
        item: dict[str, Any] = {
            "name": measure,
            "type": echarts_type,
            "data": [_to_number(row.get(measure)) for row in rows],
        }
        if stack_group:
            item["stack"] = stack_group
        if echarts_type == "line":
            item["smooth"] = rows.__len__() >= 5
            item["symbol"] = "circle"
            item["symbolSize"] = 6
        series.append(item)
    return series


def build_echarts_from_data(
    raw_data: list[dict[str, Any]],
    title: str = "Resultado de la consulta",
    recommendation: ChartRecommendation | None = None,
) -> dict[str, Any]:
    """Genera un gráfico ECharts según la forma de los datos y la recomendación."""
    if not raw_data:
        return {}

    rows = coerce_rows_for_charts(
        [dict(row) for row in raw_data if isinstance(row, dict)]
    )
    if not rows:
        return {}

    rec = recommendation or recommend_chart_type(rows)
    profile = profile_data(rows)
    keys = list(rows[0].keys())
    numeric_cols = list(profile.numeric_columns)
    text_cols = list(profile.text_columns)
    chart_type = rec.chart_type

    # Fallback: si no se detectaron medidas, forzar columnas coercibles a número
    if not numeric_cols:
        for key in keys:
            sample = [row.get(key) for row in rows]
            if any(isinstance(v, (int, float)) and not isinstance(v, bool) for v in sample):
                numeric_cols.append(key)
        text_cols = [k for k in keys if k not in numeric_cols]
        if numeric_cols:
            profile = profile_data(rows)
            # Re-recomendar con medidas ya visibles
            rec = recommendation or recommend_chart_type(rows)
            chart_type = rec.chart_type

    if not numeric_cols:
        return {}

    chart_meta = {
        "selected_type": chart_type,
        "selected_label": CHART_CATALOG.get(chart_type, {}).get("label", chart_type),
        "confidence": rec.confidence,
        "reason": rec.reason,
        "alternatives": rec.alternatives,
        "profile": {
            "rows": profile.row_count,
            "categories": profile.category_count,
            "measures": len(numeric_cols),
            "time_series": profile.is_time_series,
            "ordered_sequence": profile.is_ordered_sequence,
        },
    }

    # Valor único (KPI)
    if profile.is_single_value:
        measure = numeric_cols[0]
        value = _to_number(rows[0][measure])
        label = str(rows[0].get(text_cols[0], measure)) if text_cols else measure
        if chart_type == "gauge":
            return _build_gauge_config(value, label, title, chart_meta)
        return {
            "title": {"text": title},
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category", "data": [label]},
            "yAxis": {"type": "value"},
            "series": [{"name": measure, "type": "bar", "data": [value]}],
            "chart_meta": {**chart_meta, "selected_type": "bar", "selected_label": "KPI"},
        }

    # Fila con texto + número
    if len(rows) == 1 and len(keys) == 2 and numeric_cols and text_cols:
        cat_col, val_col = text_cols[0], numeric_cols[0]
        return {
            "title": {"text": title},
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category", "data": [str(rows[0][cat_col])]},
            "yAxis": {"type": "value"},
            "series": [{"name": val_col, "type": "bar", "data": [_to_number(rows[0][val_col])]}],
            "chart_meta": chart_meta,
        }

    # Categoría + medida(s)
    if text_cols and numeric_cols:
        cat_col = text_cols[0]
        categories = [str(row.get(cat_col, "")) for row in rows]

        if chart_type == "pie" and len(numeric_cols) == 1:
            return {
                "title": {"text": title, "left": "center", "top": 8},
                "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
                "series": [
                    {
                        "name": numeric_cols[0],
                        "type": "pie",
                        "radius": ["38%", "62%"],
                        "avoidLabelOverlap": True,
                        "data": [
                            {"name": cat, "value": _to_number(row.get(numeric_cols[0]))}
                            for cat, row in zip(categories, rows)
                        ],
                    }
                ],
                "chart_meta": chart_meta,
            }

        if chart_type == "treemap" and len(numeric_cols) == 1:
            return _build_treemap_config(
                rows,
                cat_col,
                numeric_cols[0],
                title,
                chart_meta,
            )

        if chart_type == "heatmap":
            if len(text_cols) >= 2 and len(numeric_cols) >= 1:
                return _heatmap_from_two_dimensions(
                    rows,
                    text_cols[0],
                    text_cols[1],
                    numeric_cols[0],
                    title,
                    chart_meta,
                )
            if len(text_cols) >= 1 and len(numeric_cols) >= 2:
                return _heatmap_from_category_measures(
                    rows,
                    text_cols[0],
                    numeric_cols[:8],
                    title,
                    chart_meta,
                )
            # Sin forma matricial: degradar a barras
            chart_type = "bar"
            chart_meta["selected_type"] = "bar"
            chart_meta["selected_label"] = CHART_CATALOG["bar"]["label"]
            chart_meta["reason"] = (
                f"{rec.reason} (fallback a barras: datos no matriciales para heatmap)"
            )

        if chart_type == "funnel" and len(numeric_cols) == 1:
            return _build_funnel_config(rows, cat_col, numeric_cols[0], title, chart_meta)

        if chart_type == "radar" and len(numeric_cols) >= 3:
            return _build_radar_config(rows, cat_col, numeric_cols[:8], title, chart_meta)

        if chart_type == "scatter" and len(numeric_cols) >= 2:
            return _build_scatter_config(
                rows,
                numeric_cols[0],
                numeric_cols[1],
                cat_col,
                title,
                chart_meta,
            )

        if chart_type == "candlestick":
            ohlc = _detect_ohlc_columns(numeric_cols)
            if ohlc:
                return _build_candlestick_config(rows, cat_col, ohlc, title, chart_meta)

        series = _build_series_data(rows, numeric_cols, chart_type)
        horizontal = chart_type == "bar_horizontal"

        if horizontal:
            return {
                "title": {"text": title, "left": "center", "top": 8},
                "tooltip": {"trigger": "axis"},
                "xAxis": {"type": "value"},
                "yAxis": {"type": "category", "data": categories},
                "series": series,
                "chart_meta": chart_meta,
            }

        config: dict[str, Any] = {
            "title": {"text": title, "left": "center", "top": 8},
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category", "data": categories},
            "yAxis": {"type": "value"},
            "series": series,
            "chart_meta": chart_meta,
        }
        if chart_type == "line" and len(numeric_cols) > 1:
            config["legend"] = {"show": True, "bottom": 8}
        return config

    # Solo columnas numéricas
    if numeric_cols and not text_cols:
        if chart_type == "scatter" and len(numeric_cols) >= 2:
            return _build_scatter_config(
                rows,
                numeric_cols[0],
                numeric_cols[1],
                None,
                title,
                chart_meta,
            )
        if chart_type == "radar" and len(numeric_cols) >= 3 and len(rows) == 1:
            return _build_radar_config(rows, None, numeric_cols[:8], title, chart_meta)
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
            "chart_meta": chart_meta,
        }

    return {}


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
        if chart_type in ECHARTS_SERIES_TYPES:
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

    has_treemap = any(str(s.get("type", "")).lower() == "treemap" for s in normalized)
    has_heatmap = any(str(s.get("type", "")).lower() == "heatmap" for s in normalized)
    has_gauge = any(str(s.get("type", "")).lower() == "gauge" for s in normalized)
    has_radar = any(str(s.get("type", "")).lower() == "radar" for s in normalized)
    has_funnel = any(str(s.get("type", "")).lower() == "funnel" for s in normalized)
    if has_treemap or has_heatmap or has_gauge or has_radar or has_funnel:
        config["tooltip"] = config.get("tooltip") or (
            {"position": "top"}
            if has_heatmap
            else {"trigger": "item"}
        )
        return _apply_legend_layout(config)

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
    has_treemap = any(str(s.get("type", "")).lower() == "treemap" for s in series_items)
    has_heatmap = any(str(s.get("type", "")).lower() == "heatmap" for s in series_items)
    has_gauge = any(str(s.get("type", "")).lower() == "gauge" for s in series_items)
    has_radar = any(str(s.get("type", "")).lower() == "radar" for s in series_items)
    has_funnel = any(str(s.get("type", "")).lower() == "funnel" for s in series_items)
    multi_series = len(series_items) > 1
    legend_names = _legend_series_names(config)
    needs_legend = has_pie or multi_series or len(legend_names) > 1

    if has_treemap or has_heatmap or has_gauge or (has_funnel and not needs_legend):
        config["legend"] = {"show": False}
        return config
    if has_radar and not needs_legend:
        config["legend"] = {"show": False}
        return config

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
    """
    Usa el config del LLM o genera uno desde raw_data con selección inteligente.
    Si el LLM envía un config inválido, se infiere el tipo óptimo desde los datos.
    """
    recommendation = recommend_chart_type(raw_data) if raw_data else None

    if _has_valid_chart(echarts_config):
        config = dict(echarts_config)  # type: ignore[arg-type]
        if recommendation and "chart_meta" not in config:
            config["chart_meta"] = {
                "selected_type": "llm_provided",
                "selected_label": "Configuración del agente",
                "confidence": 1.0,
                "reason": "El agente entregó echarts_config válido.",
                "suggested_type": recommendation.chart_type,
                "suggested_label": CHART_CATALOG.get(recommendation.chart_type, {}).get(
                    "label", recommendation.chart_type
                ),
                "suggested_reason": recommendation.reason,
            }
    else:
        config = build_echarts_from_data(
            raw_data,
            title=title,
            recommendation=recommendation,
        )

    return normalize_echarts_config(config)
