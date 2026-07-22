"""Phase 5 result_json contracts — ChartSpec + Report (declarative only).

Chart Spec is NEVER executable SQL/HTML. Frontend renders bar|line only.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

ChartType = Literal["bar", "line"]
ALLOWED_CHART_TYPES: frozenset[str] = frozenset({"bar", "line"})


class FieldRef(TypedDict):
    field: str
    type: str  # nominal | quantitative | temporal | ordinal


class ChartData(TypedDict):
    columns: list[str]
    rows: list[dict[str, Any]]


class ChartSpecInner(TypedDict):
    x: FieldRef
    y: FieldRef
    data: ChartData


class ChartSpec(TypedDict, total=False):
    id: str
    title: str
    type: ChartType
    spec: ChartSpecInner
    rationale: str


class ReportSection(TypedDict):
    heading: str
    body: str


class ReportDoc(TypedDict, total=False):
    title: str
    markdown: str
    sections: list[ReportSection]


def empty_result_extras() -> dict[str, Any]:
    return {"charts": [], "report": None}


def validate_chart(chart: dict[str, Any]) -> str | None:
    """Return error message if invalid, else None."""
    if not isinstance(chart, dict):
        return "chart must be an object"
    ctype = chart.get("type")
    if ctype not in ALLOWED_CHART_TYPES:
        return f"unsupported chart type {ctype!r} (allowed: bar, line)"
    spec = chart.get("spec")
    if not isinstance(spec, dict):
        return "chart.spec required"
    data = spec.get("data")
    if not isinstance(data, dict):
        return "chart.spec.data required"
    columns = data.get("columns")
    rows = data.get("rows")
    if not isinstance(columns, list) or not columns:
        return "chart.spec.data.columns must be non-empty list"
    if not isinstance(rows, list):
        return "chart.spec.data.rows must be a list"
    x = spec.get("x")
    y = spec.get("y")
    if not isinstance(x, dict) or not isinstance(y, dict):
        return "chart.spec.x and chart.spec.y required"
    xf = x.get("field")
    yf = y.get("field")
    col_set = {str(c) for c in columns}
    if xf not in col_set or yf not in col_set:
        return f"x/y fields must exist in columns (got x={xf!r} y={yf!r})"
    return None


def validate_charts(charts: list[Any], *, max_charts: int = 2) -> tuple[list[dict[str, Any]], list[str]]:
    """Filter to valid charts; return (kept, limitation messages)."""
    limitations: list[str] = []
    if not isinstance(charts, list):
        return [], ["charts must be a list — dropped"]
    kept: list[dict[str, Any]] = []
    for i, raw in enumerate(charts[:max_charts]):
        if not isinstance(raw, dict):
            limitations.append(f"charts[{i}] ignored (not an object)")
            continue
        err = validate_chart(raw)
        if err:
            limitations.append(f"charts[{i}] dropped: {err}")
            continue
        kept.append(raw)
    if len(charts) > max_charts:
        limitations.append(f"Only first {max_charts} charts kept (MVP cap)")
    return kept, limitations
