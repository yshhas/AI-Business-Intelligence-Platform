"""Smoke: heuristic ChartSpec builder + validation (no LLM / no DuckDB)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent.charts import build_charts_from_preview  # noqa: E402
from agent.contracts import validate_chart, validate_charts  # noqa: E402


def main() -> None:
    preview = {
        "columns": ["region", "total"],
        "rows": [
            {"region": "East", "total": 150},
            {"region": "West", "total": 250},
        ],
    }
    charts, lims = build_charts_from_preview(
        question="按 region 汇总",
        preview=preview,
    )
    assert charts and charts[0]["type"] == "bar", (charts, lims)
    assert validate_chart(dict(charts[0])) is None

    bad = {
        "type": "pie",
        "spec": {
            "x": {"field": "region", "type": "nominal"},
            "y": {"field": "total", "type": "quantitative"},
            "data": {"columns": ["region", "total"], "rows": []},
        },
    }
    kept, drop_lims = validate_charts([bad, dict(charts[0])])
    assert len(kept) == 1 and kept[0]["type"] == "bar", (kept, drop_lims)

    empty, elims = build_charts_from_preview(
        question="anything",
        preview={"columns": ["a"], "rows": []},
    )
    assert empty == [] and elims

    print("CHARTS_OK")


if __name__ == "__main__":
    main()
