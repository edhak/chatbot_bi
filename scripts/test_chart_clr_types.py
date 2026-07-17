"""Reproduce fallo de gráfico con tipos tipo System.Int64 de SSAS."""
from __future__ import annotations


class Int64:
    """Nombre de tipo igual a System.Int64 (pythonnet)."""

    def __init__(self, value: int) -> None:
        self._value = value

    def __str__(self) -> str:
        return str(self._value)

    # Sin __float__/__int__: como muchos wrappers CLR reales


def main() -> None:
    from agent_api.core.chart_builder import build_echarts_from_data, has_valid_chart
    from agent_api.core.chart_selector import coerce_rows_for_charts, profile_data, recommend_chart_type
    from agent_api.tools.ssas_client import _normalize_cell

    assert _normalize_cell(Int64(42)) == 42
    assert isinstance(_normalize_cell(Int64(42)), int)

    raw = [
        {"Region_Destino": "CALIFORNIA", "Total": Int64(120)},
        {"Region_Destino": "TEXAS", "Total": Int64(90)},
        {"Region_Destino": "FLORIDA", "Total": Int64(70)},
    ]
    bad_profile = profile_data(raw)
    print("before_coerce measures", bad_profile.numeric_columns, "dims", bad_profile.text_columns)

    rows = coerce_rows_for_charts(
        [{k: _normalize_cell(v) if k == "Total" else v for k, v in row.items()} for row in raw]
    )
    # Simula fila cruda CLR sin normalize previo
    raw_clr = [
        {"Region_Destino": "CALIFORNIA", "Total": Int64(120)},
        {"Region_Destino": "TEXAS", "Total": Int64(90)},
        {"Region_Destino": "FLORIDA", "Total": Int64(70)},
    ]
    rows = coerce_rows_for_charts(
        [{k: _normalize_cell(v) for k, v in row.items()} for row in raw_clr]
    )
    profile = profile_data(rows)
    print("after_coerce measures", profile.numeric_columns, "dims", profile.text_columns)
    assert "Total" in profile.numeric_columns, profile.numeric_columns

    rec = recommend_chart_type(rows)
    cfg = build_echarts_from_data(
        [{k: _normalize_cell(v) for k, v in row.items()} for row in raw_clr],
        title="test",
        recommendation=rec,
    )
    assert has_valid_chart(cfg), cfg
    print("chart_ok", cfg["series"][0]["type"], len(cfg["series"][0]["data"]))

    # Builder debe funcionar también si recibe Int64 crudos (vía coerce interno)
    cfg2 = build_echarts_from_data(raw_clr, title="test2")
    assert has_valid_chart(cfg2), cfg2
    print("chart_raw_ok", cfg2["series"][0]["type"])
    print("ALL_OK")


if __name__ == "__main__":
    main()
