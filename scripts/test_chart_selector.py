"""Validación del selector de gráficos (recommend_chart_type)."""
from __future__ import annotations

from agent_api.core.chart_selector import profile_data, recommend_chart_type

CASES: dict[str, tuple[list[dict], str]] = {
    "kpi": (
        [{"Total Ventas": 1_250_000}],
        "gauge",
    ),
    "time_line": (
        [{"Anio": y, "Ventas": 100 + y * 10} for y in range(2018, 2025)],
        "line",
    ),
    "pie": (
        [{"Region": r, "Pct": v} for r, v in zip(["N", "S", "E", "O"], [40, 30, 20, 10])],
        "pie",
    ),
    "treemap": (
        [{"Producto": f"P{i}", "Monto": 100 - i * 2} for i in range(15)],
        "treemap",
    ),
    "bar_h": (
        [
            {"Cliente": f"Cliente {i:03d} nombre largo", "Importe": 1000 - i * 10}
            for i in range(20)
        ],
        "bar_horizontal",
    ),
    "heatmap_2d": (
        [
            {"Pais": p, "Region": r, "Valor": v}
            for p in ["PE", "CL"]
            for r in ["N", "S", "C"]
            for v in [1, 2, 3]
        ],
        "heatmap",
    ),
    "stacked": (
        [{"Mes": f"M{i}", "A": i, "B": i * 2} for i in range(1, 7)],
        "bar_stacked",
    ),
    "scatter": (
        [{"Costo": i * 10, "Precio": i * 12 + 5} for i in range(1, 11)],
        "scatter",
    ),
    "radar": (
        [{"Equipo": "A", "M1": 1, "M2": 2, "M3": 3, "M4": 4, "M5": 5}],
        "radar",
    ),
    "funnel_bad": (
        [{"Region": f"R{i}", "Cant": 100 - i * 10} for i in range(5)],
        "bar",
    ),
    "funnel_good": (
        [
            {"Etapa": e, "Leads": v}
            for e, v in zip(["Visitas", "Registro", "Demo", "Cierre"], [1000, 400, 120, 30])
        ],
        "funnel",
    ),
    "candlestick": (
        [
            {
                "Fecha": f"2024-0{i + 1}-01",
                "Open": 10 + i,
                "High": 12 + i,
                "Low": 9 + i,
                "Close": 11 + i,
            }
            for i in range(6)
        ],
        "candlestick",
    ),
    "nominal_bar": (
        [{"Equipo": f"E{i}", "Horas": i * 3} for i in range(1, 9)],
        "bar",
    ),
}


def main() -> None:
    ok = 0
    fail = 0
    for name, (rows, expected) in CASES.items():
        rec = recommend_chart_type(rows)
        prof = profile_data(rows)
        passed = rec.chart_type == expected
        status = "OK" if passed else "FAIL"
        if passed:
            ok += 1
        else:
            fail += 1
        print(f"[{status}] {name:14} expected={expected:15} got={rec.chart_type:15} ({rec.confidence})")
        print(f"         profile: cats={prof.category_count} meas={len(prof.numeric_columns)} "
              f"time={prof.is_time_series} ord={prof.is_ordered_sequence}")
        print(f"         reason: {rec.reason}")
        if rec.alternatives:
            alt = ", ".join(f"{a['type']}({a['score']})" for a in rec.alternatives[:3])
            print(f"         alts: {alt}")
        print()
    print(f"Resultado: {ok} OK, {fail} FAIL de {ok + fail}")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
