"""Deterministic ChartSpec builder from table_preview (no LLM structure)."""

from __future__ import annotations

from typing import Any

from agent.contracts import ChartSpec, validate_chart

_DIM_HINTS = {
    "region",
    "area",
    "category",
    "product",
    "name",
    "dim",
    "city",
    "country",
    "month",
    "date",
    "day",
    "week",
}
_METRIC_HINTS = {
    "amount",
    "sales",
    "revenue",
    "qty",
    "quantity",
    "total",
    "value",
    "count",
    "sum",
    "avg",
    "mean",
}
_TEMPORAL_HINTS = {"date", "day", "month", "week", "year", "time", "timestamp"}


def build_charts_from_preview(
    *,
    question: str,
    preview: dict[str, Any],
    max_charts: int = 2,
    max_rows: int = 50,
) -> tuple[list[ChartSpec], list[str]]:
    """Heuristic ChartSpec list. Never invents columns absent from preview."""
    limitations: list[str] = []
    columns = [str(c) for c in (preview.get("columns") or [])]
    rows_raw = preview.get("rows") or []
    if not columns:
        return [], ["No columns in preview — skipped charts"]
    if not isinstance(rows_raw, list) or not rows_raw:
        return [], ["No rows in preview — skipped charts"]

    rows: list[dict[str, Any]] = []
    for r in rows_raw[:max_rows]:
        if isinstance(r, dict):
            rows.append({k: r.get(k) for k in columns})

    dim, metric = _pick_fields(columns, rows)
    if not dim or not metric:
        return [], [
            "Could not infer dimension+metric from preview — skipped charts"
        ]

    chart_type = _pick_type(question=question, dim=dim)
    data_rows = _coerce_metric_rows(rows, dim=dim, metric=metric)
    if not data_rows:
        return [], ["No numeric metric values for chart — skipped charts"]

    chart: ChartSpec = {
        "id": "chart_1",
        "title": f"{metric} by {dim}",
        "type": chart_type,
        "spec": {
            "x": {
                "field": dim,
                "type": "temporal" if _is_temporal_name(dim) else "nominal",
            },
            "y": {"field": metric, "type": "quantitative"},
            "data": {"columns": [dim, metric], "rows": data_rows},
        },
        "rationale": (
            f"Heuristic: mapped dimension `{dim}` and metric `{metric}` "
            f"to a {chart_type} chart from query preview."
        ),
    }
    err = validate_chart(dict(chart))
    if err:
        return [], [f"Chart validation failed: {err}"]

    charts: list[ChartSpec] = [chart]
    # Optional second chart: if >2 numeric cols and another metric exists
    if max_charts >= 2:
        alt = _alt_metric(columns, rows, exclude=metric)
        if alt:
            data2 = _coerce_metric_rows(rows, dim=dim, metric=alt)
            if data2:
                c2: ChartSpec = {
                    "id": "chart_2",
                    "title": f"{alt} by {dim}",
                    "type": chart_type,
                    "spec": {
                        "x": {
                            "field": dim,
                            "type": "temporal" if _is_temporal_name(dim) else "nominal",
                        },
                        "y": {"field": alt, "type": "quantitative"},
                        "data": {"columns": [dim, alt], "rows": data2},
                    },
                    "rationale": f"Secondary metric `{alt}` with same dimension `{dim}`.",
                }
                if validate_chart(dict(c2)) is None:
                    charts.append(c2)

    return charts[:max_charts], limitations


def enhance_chart_copy(
    charts: list[ChartSpec],
    *,
    question: str,
    summary: str,
    llm_fn: Any | None = None,
) -> list[ChartSpec]:
    """Optionally rewrite title/rationale via LLM callback; never touches spec."""
    if not charts or llm_fn is None:
        return charts
    out: list[ChartSpec] = []
    for ch in charts:
        try:
            title, rationale = llm_fn(
                question=question,
                summary=summary,
                chart_type=ch.get("type"),
                fields=(ch.get("spec") or {}).get("x", {}).get("field"),
                metric=(ch.get("spec") or {}).get("y", {}).get("field"),
                old_title=ch.get("title"),
            )
            updated = dict(ch)
            if title:
                updated["title"] = str(title)[:120]
            if rationale:
                updated["rationale"] = str(rationale)[:400]
            out.append(updated)  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001
            out.append(ch)
    return out


def _pick_fields(
    columns: list[str], rows: list[dict[str, Any]]
) -> tuple[str | None, str | None]:
    numeric: list[str] = []
    categorical: list[str] = []
    for c in columns:
        if _column_looks_numeric(c, rows):
            numeric.append(c)
        else:
            categorical.append(c)

    dim = next((c for c in categorical if c.lower() in _DIM_HINTS), None)
    if dim is None and categorical:
        dim = categorical[0]
    if dim is None and len(columns) >= 2:
        # fallback: first non-numeric-looking as dim
        dim = next((c for c in columns if c not in numeric), columns[0])

    metric = next((c for c in numeric if c.lower() in _METRIC_HINTS), None)
    if metric is None and numeric:
        metric = numeric[0]
    if metric is None:
        # try coerce second column
        for c in columns:
            if c != dim and _column_looks_numeric(c, rows):
                metric = c
                break
    if dim == metric:
        return None, None
    return dim, metric


def _alt_metric(
    columns: list[str], rows: list[dict[str, Any]], *, exclude: str
) -> str | None:
    for c in columns:
        if c != exclude and _column_looks_numeric(c, rows):
            return c
    return None


def _pick_type(*, question: str, dim: str) -> str:
    q = question.lower()
    if _is_temporal_name(dim) or any(k in q for k in ("趋势", "trend", "over time", "时间")):
        return "line"
    return "bar"


def _is_temporal_name(name: str) -> bool:
    n = name.lower()
    return any(h in n for h in _TEMPORAL_HINTS)


def _column_looks_numeric(col: str, rows: list[dict[str, Any]]) -> bool:
    if col.lower() in _METRIC_HINTS:
        return True
    nums = 0
    seen = 0
    for r in rows[:20]:
        v = r.get(col)
        if v is None or v == "":
            continue
        seen += 1
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            nums += 1
        else:
            try:
                float(str(v).replace(",", ""))
                nums += 1
            except ValueError:
                pass
    return seen > 0 and nums / seen >= 0.8


def _coerce_metric_rows(
    rows: list[dict[str, Any]], *, dim: str, metric: str
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        x = r.get(dim)
        y = r.get(metric)
        if x is None or y is None:
            continue
        try:
            if isinstance(y, bool):
                continue
            yv = float(y) if not isinstance(y, (int, float)) else float(y)
        except (TypeError, ValueError):
            continue
        out.append({dim: x if not isinstance(x, float) else x, metric: yv})
    return out
