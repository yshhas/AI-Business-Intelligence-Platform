"""Unit tests for agent.charts — deterministic ChartSpec builder.

Tests cover field selection (dimension/metric), chart type inference,
data coercion, edge cases (empty data, single column), and JSON
serializability. No LLM / database / external dependencies.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from agent.charts import (
    _alt_metric,
    _coerce_metric_rows,
    _column_looks_numeric,
    _pick_fields,
    _pick_type,
    build_charts_from_preview,
    enhance_chart_copy,
)


# ── Helpers ──────────────────────────────────────────────────────────────

def _numeric_rows(cols: list[str], values: list[list]) -> list[dict]:
    return [dict(zip(cols, row)) for row in values]


# ── build_charts_from_preview ────────────────────────────────────────────

class TestBuildChartsFromPreview:
    """Main entry point: returns (charts, limitations)."""

    def test_empty_columns_returns_no_charts(self, make_preview):
        preview = make_preview([], [])
        charts, lims = build_charts_from_preview(
            question="Show sales", preview=preview
        )
        assert charts == []
        assert any("No columns" in l for l in lims)

    def test_empty_rows_returns_no_charts(self, make_preview):
        preview = make_preview(["region", "amount"], [])
        charts, lims = build_charts_from_preview(
            question="Show sales", preview=preview
        )
        assert charts == []
        assert any("No rows" in l for l in lims)

    def test_basic_bar_chart(self, make_preview):
        preview = make_preview(
            ["region", "amount"],
            _numeric_rows(["region", "amount"], [["East", 500], ["West", 300]]),
        )
        charts, lims = build_charts_from_preview(
            question="Show sales by region", preview=preview
        )
        assert len(charts) == 1
        c = charts[0]
        assert c["type"] == "bar"
        assert c["title"] == "amount by region"
        assert c["spec"]["x"]["field"] == "region"
        assert c["spec"]["y"]["field"] == "amount"
        assert len(c["spec"]["data"]["rows"]) == 2
        assert lims == []  # no limitations for successful build

    def test_temporal_dimension_yields_line_chart(self, make_preview):
        preview = make_preview(
            ["order_date", "amount"],
            _numeric_rows(["order_date", "amount"], [["2024-01", 500], ["2024-02", 300]]),
        )
        charts, _ = build_charts_from_preview(
            question="Show sales", preview=preview
        )
        assert charts[0]["type"] == "line"

    def test_trend_question_yields_line_chart(self, make_preview):
        preview = make_preview(
            ["region", "amount"],
            _numeric_rows(["region", "amount"], [["East", 500], ["West", 300]]),
        )
        charts, _ = build_charts_from_preview(
            question="Show sales trend over time", preview=preview
        )
        # "trend" in question → line even with non-temporal dim
        assert charts[0]["type"] == "line"

    def test_two_charts_with_alt_metric(self, make_preview):
        preview = make_preview(
            ["region", "amount", "qty"],
            _numeric_rows(
                ["region", "amount", "qty"],
                [["East", 500, 10], ["West", 300, 7]],
            ),
        )
        charts, _ = build_charts_from_preview(
            question="Show sales", preview=preview, max_charts=2
        )
        assert len(charts) == 2
        assert charts[0]["spec"]["y"]["field"] == "amount"
        assert charts[1]["spec"]["y"]["field"] == "qty"

    def test_cannot_infer_dimension_and_metric(self, make_preview):
        preview = make_preview(
            ["col1"],
            _numeric_rows(["col1"], [["a"], ["b"]]),
        )
        charts, lims = build_charts_from_preview(
            question="Show data", preview=preview
        )
        assert charts == []
        assert any("Could not infer" in l for l in lims)

    def test_rows_capped_at_max_rows(self, make_preview):
        preview = make_preview(
            ["region", "amount"],
            _numeric_rows(["region", "amount"], [["R", i] for i in range(100)]),
        )
        charts, _ = build_charts_from_preview(
            question="Show sales", preview=preview, max_rows=10
        )
        assert len(charts[0]["spec"]["data"]["rows"]) == 10

    def test_non_dict_rows_skipped(self):
        preview = {"columns": ["region", "amount"], "rows": [None, "bad", {"region": "E", "amount": 100}]}
        charts, _ = build_charts_from_preview(
            question="Show sales", preview=preview
        )
        assert len(charts) == 1
        assert len(charts[0]["spec"]["data"]["rows"]) == 1

    def test_chart_is_json_serializable(self, make_preview):
        preview = make_preview(
            ["region", "amount"],
            _numeric_rows(["region", "amount"], [["East", 500.5]]),
        )
        charts, _ = build_charts_from_preview(
            question="Show sales", preview=preview
        )
        # Must not raise TypeError
        dumped = json.dumps(charts)
        assert "East" in dumped
        assert "500.5" in dumped


# ── _pick_fields ─────────────────────────────────────────────────────────

class TestPickFields:
    """Dimension + metric selection logic."""

    def test_picks_hinted_dimension(self):
        rows = [{"region": "E", "amount": 100}]
        dim, metric = _pick_fields(["region", "amount"], rows)
        assert dim == "region"

    def test_picks_hinted_metric(self):
        rows = [{"region": "E", "amount": 100}]
        dim, metric = _pick_fields(["region", "amount"], rows)
        assert metric == "amount"

    def test_fallback_dimension_first_categorical(self):
        rows = [{"dept": "Sales", "budget": 1000}]
        dim, _ = _pick_fields(["budget", "dept"], rows)
        assert dim == "dept"

    def test_fallback_metric_first_numeric(self):
        rows = [{"dept": "Sales", "value": 1000}]
        _, metric = _pick_fields(["dept", "value"], rows)
        assert metric == "value"

    def test_single_column_returns_no_dim(self):
        """Single numeric column → dim=None, metric=column (no pair to chart)."""
        rows = [{"x": 1}]
        dim, metric = _pick_fields(["x"], rows)
        assert dim is None
        assert metric == "x"  # numeric column assigned as metric

    def test_all_string_columns_no_metric(self):
        rows = [{"a": "x", "b": "y"}]
        dim, metric = _pick_fields(["a", "b"], rows)
        # metric is None, dim is still selected
        assert dim is not None
        assert metric is None


# ── _pick_type ───────────────────────────────────────────────────────────

class TestPickType:
    """Chart type inference (bar vs line)."""

    def test_default_bar(self):
        assert _pick_type(question="Show sales", dim="region") == "bar"

    def test_temporal_dim_line(self):
        assert _pick_type(question="Show sales", dim="order_date") == "line"

    def test_trend_in_question_line(self):
        assert _pick_type(question="sales trend", dim="region") == "line"


# ── _column_looks_numeric ────────────────────────────────────────────────

class TestColumnLooksNumeric:
    """Numeric column detection heuristics."""

    def test_metric_hint_name(self):
        assert _column_looks_numeric("amount", [{"amount": "x"}]) is True

    def test_actual_numbers(self):
        rows = [{"val": 100}, {"val": 200}]
        assert _column_looks_numeric("val", rows) is True

    def test_float_numbers(self):
        rows = [{"val": 1.5}, {"val": 2.5}]
        assert _column_looks_numeric("val", rows) is True

    def test_string_numbers(self):
        rows = [{"val": "100"}, {"val": "200.5"}]
        assert _column_looks_numeric("val", rows) is True

    def test_non_numeric_strings(self):
        rows = [{"name": "Alice"}, {"name": "Bob"}]
        assert _column_looks_numeric("name", rows) is False

    def test_boolean_is_not_numeric(self):
        rows = [{"flag": True}, {"flag": False}]
        # bool is instance of int, but _column_looks_numeric excludes it
        assert _column_looks_numeric("flag", rows) is False

    def test_empty_rows(self):
        assert _column_looks_numeric("x", []) is False


# ── _coerce_metric_rows ──────────────────────────────────────────────────

class TestCoerceMetricRows:
    """Row coercion for chart data."""

    def test_normal_rows(self):
        rows = [{"region": "E", "amount": 100}, {"region": "W", "amount": 200}]
        result = _coerce_metric_rows(rows, dim="region", metric="amount")
        assert len(result) == 2
        assert result[0] == {"region": "E", "amount": 100.0}

    def test_null_values_skipped(self):
        rows = [{"region": "E", "amount": None}, {"region": "W", "amount": 200}]
        result = _coerce_metric_rows(rows, dim="region", metric="amount")
        assert len(result) == 1

    def test_boolean_skipped(self):
        rows = [{"region": "E", "amount": True}]
        result = _coerce_metric_rows(rows, dim="region", metric="amount")
        assert result == []


# ── _alt_metric ──────────────────────────────────────────────────────────

class TestAltMetric:
    """Secondary metric detection."""

    def test_finds_alt_metric(self):
        rows = [{"region": "E", "amount": 100, "qty": 5}]
        alt = _alt_metric(["region", "amount", "qty"], rows, exclude="amount")
        assert alt == "qty"

    def test_no_alt_metric(self):
        rows = [{"region": "E", "amount": 100}]
        alt = _alt_metric(["region", "amount"], rows, exclude="amount")
        assert alt is None


# ── enhance_chart_copy ───────────────────────────────────────────────────

class TestEnhanceChartCopy:
    """LLM-enhanced chart title/rationale (optional)."""

    def test_no_llm_returns_original(self):
        charts = [{"id": "c1", "type": "bar", "title": "T"}]
        result = enhance_chart_copy(charts, question="Q", summary="S")
        assert result[0]["title"] == "T"

    def test_llm_updates_title(self):
        charts = [{"id": "c1", "type": "bar", "title": "orig"}]
        llm_fn = MagicMock(return_value=("New Title", "Because"))
        result = enhance_chart_copy(charts, question="Q", summary="S", llm_fn=llm_fn)
        assert result[0]["title"] == "New Title"
        assert result[0]["rationale"] == "Because"

    def test_llm_exception_returns_original(self):
        charts = [{"id": "c1", "type": "bar", "title": "T"}]
        llm_fn = MagicMock(side_effect=RuntimeError("fail"))
        result = enhance_chart_copy(charts, question="Q", summary="S", llm_fn=llm_fn)
        assert result[0]["title"] == "T"