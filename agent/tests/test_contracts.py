"""Unit tests for agent.contracts — ChartSpec validation & TypedDict definitions.

Tests cover:
- All TypedDict types (construction, optional fields, serialization)
- empty_result_extras
- validate_chart: all 8 validation paths + edge cases
- validate_charts: filtering, limitations, max_charts cap
- Cross-module compatibility: how charts.py / pipeline.py consume these types
"""

from __future__ import annotations

import json

import pytest

from agent.contracts import (
    ALLOWED_CHART_TYPES,
    ChartData,
    ChartSpec,
    ChartSpecInner,
    ChartType,
    FieldRef,
    ReportDoc,
    ReportSection,
    empty_result_extras,
    validate_chart,
    validate_charts,
)


# ═══════════════════════════════════════════════════════════════════════
# TypedDict construction & behaviour
# ═══════════════════════════════════════════════════════════════════════

class TestFieldRef:
    def test_valid_construction(self):
        ref: FieldRef = {"field": "region", "type": "nominal"}
        assert ref["field"] == "region"
        assert ref["type"] == "nominal"

    def test_json_serializable(self):
        ref: FieldRef = {"field": "amount", "type": "quantitative"}
        dumped = json.dumps(ref)
        assert json.loads(dumped) == ref

    def test_default_dict_behaviour(self):
        """TypedDict is plain dict at runtime — no validation."""
        ref = FieldRef(field="region", type="nominal")  # type: ignore[call-arg]
        assert ref["field"] == "region"

    def test_extra_key_accepted(self):
        """TypedDict is plain dict at runtime — extra keys are allowed."""
        ref = {"field": "x", "type": "nominal", "extra": 123}
        assert ref["extra"] == 123

    def test_missing_field_accepted(self):
        """TypedDict is plain dict at runtime — missing keys are allowed."""
        ref = {"field": "x"}  # missing 'type'
        assert ref["field"] == "x"
        assert "type" not in ref


class TestChartData:
    def test_valid_construction(self):
        data: ChartData = {
            "columns": ["region", "amount"],
            "rows": [{"region": "East", "amount": 100}],
        }
        assert data["columns"] == ["region", "amount"]
        assert len(data["rows"]) == 1

    def test_empty_rows_allowed(self):
        data: ChartData = {"columns": ["col"], "rows": []}
        assert data["rows"] == []


class TestChartSpecInner:
    def test_valid_construction(self):
        inner: ChartSpecInner = {
            "x": {"field": "region", "type": "nominal"},
            "y": {"field": "amount", "type": "quantitative"},
            "data": {"columns": ["region", "amount"], "rows": []},
        }
        assert inner["x"]["field"] == "region"
        assert inner["y"]["field"] == "amount"


class TestChartSpec:
    def test_all_fields(self):
        spec: ChartSpec = {
            "id": "chart_1",
            "title": "Sales by Region",
            "type": "bar",
            "rationale": "Shows regional distribution",
            "spec": {
                "x": {"field": "region", "type": "nominal"},
                "y": {"field": "amount", "type": "quantitative"},
                "data": {"columns": ["region", "amount"], "rows": []},
            },
        }
        assert spec["id"] == "chart_1"
        assert spec["type"] == "bar"

    def test_minimal_fields(self):
        """total=False means all fields are optional."""
        spec: ChartSpec = {"type": "bar"}
        assert spec["type"] == "bar"
        assert "spec" not in spec

    def test_empty_dict(self):
        spec: ChartSpec = {}
        assert isinstance(spec, dict)


class TestReportSection:
    def test_valid_construction(self):
        section: ReportSection = {"heading": "Overview", "body": "This is the body."}
        assert section["heading"] == "Overview"


class TestReportDoc:
    def test_valid_with_markdown(self):
        doc: ReportDoc = {"title": "Report", "markdown": "# Hello"}
        assert doc["title"] == "Report"

    def test_valid_with_sections(self):
        doc: ReportDoc = {
            "title": "Report",
            "sections": [{"heading": "H1", "body": "B1"}],
        }
        assert len(doc["sections"]) == 1

    def test_total_false_allows_empty(self):
        doc: ReportDoc = {}
        assert isinstance(doc, dict)


# ═══════════════════════════════════════════════════════════════════════
# ChartType & ALLOWED_CHART_TYPES
# ═══════════════════════════════════════════════════════════════════════

class TestChartType:
    def test_bar_allowed(self):
        assert "bar" in ALLOWED_CHART_TYPES

    def test_line_allowed(self):
        assert "line" in ALLOWED_CHART_TYPES

    def test_only_two_types(self):
        assert len(ALLOWED_CHART_TYPES) == 2

    def test_pie_not_allowed(self):
        assert "pie" not in ALLOWED_CHART_TYPES

    def test_scatter_not_allowed(self):
        assert "scatter" not in ALLOWED_CHART_TYPES

    def test_is_frozenset(self):
        assert isinstance(ALLOWED_CHART_TYPES, frozenset)


# ═══════════════════════════════════════════════════════════════════════
# empty_result_extras
# ═══════════════════════════════════════════════════════════════════════

class TestEmptyResultExtras:
    def test_returns_dict(self):
        result = empty_result_extras()
        assert isinstance(result, dict)

    def test_empty_charts(self):
        result = empty_result_extras()
        assert result["charts"] == []

    def test_null_report(self):
        result = empty_result_extras()
        assert result["report"] is None

    def test_each_call_returns_new_dict(self):
        a = empty_result_extras()
        b = empty_result_extras()
        assert a is not b
        assert a == b


# ═══════════════════════════════════════════════════════════════════════
# validate_chart — all 8 validation paths
# ═══════════════════════════════════════════════════════════════════════

_VALID_CHART = {
    "type": "bar",
    "spec": {
        "x": {"field": "region", "type": "nominal"},
        "y": {"field": "amount", "type": "quantitative"},
        "data": {
            "columns": ["region", "amount"],
            "rows": [{"region": "East", "amount": 100}],
        },
    },
}


class TestValidateChart:
    # --- Path 1: not a dict ---

    def test_not_a_dict(self):
        assert validate_chart("not a chart") == "chart must be an object"  # type: ignore[arg-type]
        assert validate_chart(123) == "chart must be an object"  # type: ignore[arg-type]
        assert validate_chart(None) == "chart must be an object"  # type: ignore[arg-type]
        assert validate_chart([]) == "chart must be an object"  # type: ignore[arg-type]

    # --- Path 2: unsupported chart type ---

    def test_missing_type(self):
        chart = {"spec": _VALID_CHART["spec"]}
        err = validate_chart(chart)
        assert err is not None
        assert "unsupported chart type" in err
        assert "None" in err

    def test_unsupported_pie(self):
        chart = {**_VALID_CHART, "type": "pie"}
        err = validate_chart(chart)
        assert "unsupported chart type" in err
        assert "pie" in err

    def test_unsupported_scatter(self):
        chart = {**_VALID_CHART, "type": "scatter"}
        err = validate_chart(chart)
        assert "unsupported chart type" in err

    # --- Path 3: spec missing / not dict ---

    def test_spec_missing(self):
        chart = {"type": "bar"}
        err = validate_chart(chart)
        assert err == "chart.spec required"

    def test_spec_not_dict(self):
        chart = {"type": "bar", "spec": "not_a_dict"}
        err = validate_chart(chart)
        assert err == "chart.spec required"

    # --- Path 4: data missing / not dict ---

    def test_data_missing(self):
        chart = {"type": "bar", "spec": {"x": {}, "y": {}}}
        err = validate_chart(chart)
        assert err == "chart.spec.data required"

    def test_data_not_dict(self):
        chart = {
            "type": "bar",
            "spec": {"x": {}, "y": {}, "data": ["not", "dict"]},
        }
        err = validate_chart(chart)
        assert err == "chart.spec.data required"

    # --- Path 5: columns empty or missing ---

    def test_columns_missing(self):
        chart = {
            "type": "bar",
            "spec": {"x": {}, "y": {}, "data": {"rows": []}},
        }
        err = validate_chart(chart)
        assert "columns must be non-empty list" in err

    def test_columns_empty_list(self):
        chart = {
            "type": "bar",
            "spec": {
                "x": {},
                "y": {},
                "data": {"columns": [], "rows": []},
            },
        }
        err = validate_chart(chart)
        assert "columns must be non-empty list" in err

    def test_columns_not_list(self):
        chart = {
            "type": "bar",
            "spec": {
                "x": {},
                "y": {},
                "data": {"columns": "not_list", "rows": []},
            },
        }
        err = validate_chart(chart)
        assert "columns must be non-empty list" in err

    # --- Path 6: rows not a list ---

    def test_rows_missing(self):
        chart = {
            "type": "bar",
            "spec": {
                "x": {},
                "y": {},
                "data": {"columns": ["col"]},
            },
        }
        err = validate_chart(chart)
        assert err == "chart.spec.data.rows must be a list"

    def test_rows_not_list(self):
        chart = {
            "type": "bar",
            "spec": {
                "x": {},
                "y": {},
                "data": {"columns": ["col"], "rows": "not_list"},
            },
        }
        err = validate_chart(chart)
        assert err == "chart.spec.data.rows must be a list"

    # --- Path 7: x or y missing / not dict ---

    def test_x_missing(self):
        chart = {
            "type": "bar",
            "spec": {
                "y": {"field": "amount"},
                "data": {"columns": ["amount"], "rows": []},
            },
        }
        err = validate_chart(chart)
        assert "chart.spec.x and chart.spec.y required" in err

    def test_y_missing(self):
        chart = {
            "type": "bar",
            "spec": {
                "x": {"field": "region"},
                "data": {"columns": ["region"], "rows": []},
            },
        }
        err = validate_chart(chart)
        assert "chart.spec.x and chart.spec.y required" in err

    def test_x_not_dict(self):
        chart = {
            "type": "bar",
            "spec": {
                "x": "not_dict",
                "y": {"field": "amount"},
                "data": {"columns": ["amount"], "rows": []},
            },
        }
        err = validate_chart(chart)
        assert "chart.spec.x and chart.spec.y required" in err

    # --- Path 8: x/y field not in columns ---

    def test_x_field_not_in_columns(self):
        chart = {
            "type": "bar",
            "spec": {
                "x": {"field": "missing_col"},
                "y": {"field": "amount"},
                "data": {"columns": ["region", "amount"], "rows": []},
            },
        }
        err = validate_chart(chart)
        assert "x/y fields must exist in columns" in err

    def test_y_field_not_in_columns(self):
        chart = {
            "type": "bar",
            "spec": {
                "x": {"field": "region"},
                "y": {"field": "missing_col"},
                "data": {"columns": ["region", "amount"], "rows": []},
            },
        }
        err = validate_chart(chart)
        assert "x/y fields must exist in columns" in err

    # --- Valid cases ---

    def test_valid_bar_chart(self):
        assert validate_chart(_VALID_CHART) is None

    def test_valid_line_chart(self):
        chart = {**_VALID_CHART, "type": "line"}
        assert validate_chart(chart) is None

    def test_valid_with_empty_rows(self):
        chart = {
            "type": "bar",
            "spec": {
                "x": {"field": "region", "type": "nominal"},
                "y": {"field": "amount", "type": "quantitative"},
                "data": {"columns": ["region", "amount"], "rows": []},
            },
        }
        assert validate_chart(chart) is None

    def test_valid_with_extra_fields(self):
        """Extra fields (id, title, rationale) are ignored by validation."""
        chart = {
            **_VALID_CHART,
            "id": "chart_1",
            "title": "Sales",
            "rationale": "Shows distribution",
            "extra_field": "ignored",
        }
        assert validate_chart(chart) is None

    def test_valid_with_single_column(self):
        """Single column chart is valid if x/y point to same column."""
        chart = {
            "type": "bar",
            "spec": {
                "x": {"field": "value"},
                "y": {"field": "value"},
                "data": {"columns": ["value"], "rows": []},
            },
        }
        assert validate_chart(chart) is None

    # --- Edge cases ---

    def test_type_case_sensitive(self):
        """'BAR' is not 'bar' — ALLOWED_CHART_TYPES is case-sensitive."""
        chart = {**_VALID_CHART, "type": "BAR"}
        err = validate_chart(chart)
        assert "unsupported chart type" in err

    def test_type_mixed_case(self):
        chart = {**_VALID_CHART, "type": "Bar"}
        err = validate_chart(chart)
        assert "unsupported chart type" in err

    def test_columns_contains_non_string(self):
        """Columns with non-string entries still work via str() coercion."""
        chart = {
            "type": "bar",
            "spec": {
                "x": {"field": "1"},
                "y": {"field": "2"},
                "data": {"columns": [1, 2], "rows": []},
            },
        }
        # col_set = {str(c) for c in columns} → {"1", "2"}
        # xf = "1", yf = "2" → both in col_set → valid
        assert validate_chart(chart) is None

    def test_columns_coerced_to_string(self):
        """str(c) coercion means int 1 matches str '1'."""
        chart = {
            "type": "bar",
            "spec": {
                "x": {"field": 1},
                "y": {"field": "amount"},
                "data": {"columns": [1, "amount"], "rows": []},
            },
        }
        # col_set = {"1", "amount"}, xf = 1, yf = "amount"
        # 1 in {"1", "amount"} is False! (int != str)
        # Wait, let me check: x.get("field") returns 1 (int), not "1"
        # col_set = {str(1)} = {"1"}
        # 1 in {"1", "amount"} → False
        # So this should fail...
        err = validate_chart(chart)
        # Actually, the field is 1 (int), and str(1) = "1"
        # But col_set is {str(c) for c in [1, "amount"]} = {"1", "amount"}
        # xf = 1 (int), "1" in col_set is True, but 1 in col_set is False
        # So xf=1 not in {"1", "amount"} → error
        assert err is not None
        assert "x/y fields must exist in columns" in err


# ═══════════════════════════════════════════════════════════════════════
# validate_charts
# ═══════════════════════════════════════════════════════════════════════

class TestValidateCharts:
    def test_all_valid(self):
        kept, limitations = validate_charts([_VALID_CHART])
        assert len(kept) == 1
        assert limitations == []

    def test_mixed_valid_and_invalid(self):
        """max_charts=2: only indices 0,1 processed. Index 0 valid, index 1 invalid."""
        charts = [
            _VALID_CHART,
            {"type": "pie"},  # invalid at index 1
            _VALID_CHART,  # index 2 — beyond max_charts, not processed
        ]
        kept, limitations = validate_charts(charts)
        assert len(kept) == 1
        assert len(limitations) == 2
        assert "unsupported chart type" in limitations[0]

    def test_not_a_list(self):
        kept, limitations = validate_charts("not_a_list")  # type: ignore[arg-type]
        assert kept == []
        assert "must be a list" in limitations[0]

    def test_none_input(self):
        kept, limitations = validate_charts(None)  # type: ignore[arg-type]
        assert kept == []
        assert "must be a list" in limitations[0]

    def test_empty_list(self):
        kept, limitations = validate_charts([])
        assert kept == []
        assert limitations == []

    def test_not_dict_item(self):
        """max_charts=2: only indices 0,1 processed. Both invalid + cap warning."""
        charts = [{"type": "bar"}, "not_a_dict", _VALID_CHART]
        kept, limitations = validate_charts(charts)
        assert len(kept) == 0
        assert len(limitations) == 3  # 2 errors + 1 cap warning
        assert "not an object" in limitations[1]

    # --- max_charts cap ---

    def test_max_charts_default_2(self):
        charts = [_VALID_CHART, _VALID_CHART, _VALID_CHART]
        kept, limitations = validate_charts(charts)
        assert len(kept) == 2
        assert "Only first 2 charts kept" in limitations[-1]

    def test_max_charts_custom(self):
        charts = [_VALID_CHART, _VALID_CHART, _VALID_CHART, _VALID_CHART]
        kept, limitations = validate_charts(charts, max_charts=3)
        assert len(kept) == 3
        assert "Only first 3 charts kept" in limitations[-1]

    def test_max_charts_one(self):
        charts = [_VALID_CHART, _VALID_CHART]
        kept, limitations = validate_charts(charts, max_charts=1)
        assert len(kept) == 1
        assert len(limitations) == 1
        assert "first 1 charts kept" in limitations[0]

    def test_max_charts_zero(self):
        """max_charts=0 means no charts are kept."""
        charts = [_VALID_CHART]
        kept, limitations = validate_charts(charts, max_charts=0)
        assert kept == []
        assert "first 0 charts kept" in limitations[0]

    # --- Limitations ordering ---

    def test_limitations_ordered_by_index(self):
        charts = [
            {"type": "pie"},  # idx 0 — invalid
            _VALID_CHART,  # idx 1 — valid
            {"type": "scatter"},  # idx 2 — invalid
        ]
        kept, limitations = validate_charts(charts)
        assert len(kept) == 1
        # idx 0 error first, idx 2 error second (but idx 2 is at index 2, which is >= max_charts=2... wait, max_charts=2, so it processes indices 0 and 1 only)
        # Actually, max_charts=2, so it processes 0 and 1. Index 2 is beyond max_charts.
        # The "Only first 2 charts kept" limitation is added after the loop.
        # So limitations: ["charts[0] dropped: unsupported chart type 'pie'", "Only first 2 charts kept (MVP cap)"]
        assert len(limitations) == 2
        assert "charts[0]" in limitations[0]

    def test_limitations_include_index(self):
        charts = [
            _VALID_CHART,
            {"type": "pie"},  # idx 1
        ]
        kept, limitations = validate_charts(charts)
        assert len(limitations) == 1
        assert "charts[1]" in limitations[0]

    def test_limitations_include_reason(self):
        charts = [{"type": "bar"}]  # missing spec
        kept, limitations = validate_charts(charts)
        assert len(limitations) == 1
        assert "chart.spec required" in limitations[0]


# ═══════════════════════════════════════════════════════════════════════
# Integration: contract compatibility across modules
# ═══════════════════════════════════════════════════════════════════════

class TestCrossModuleCompatibility:
    """Verify that contracts can be consumed as expected by callers."""

    def test_chart_spec_is_json_serializable(self):
        """ChartSpec must be serializable for API responses."""
        spec: ChartSpec = {
            "id": "c1",
            "title": "Sales",
            "type": "bar",
            "spec": {
                "x": {"field": "region", "type": "nominal"},
                "y": {"field": "amount", "type": "quantitative"},
                "data": {
                    "columns": ["region", "amount"],
                    "rows": [{"region": "East", "amount": 100}],
                },
            },
        }
        json_str = json.dumps(spec)
        restored = json.loads(json_str)
        assert restored["type"] == "bar"
        assert restored["spec"]["data"]["rows"][0]["amount"] == 100

    def test_report_doc_is_json_serializable(self):
        doc: ReportDoc = {
            "title": "Analysis",
            "markdown": "# Report",
            "sections": [{"heading": "Overview", "body": "Content"}],
        }
        json_str = json.dumps(doc)
        restored = json.loads(json_str)
        assert restored["title"] == "Analysis"

    def test_validate_chart_accepts_chart_spec(self):
        """validate_chart should accept a ChartSpec-compatible dict."""
        spec: ChartSpec = {
            "id": "c1",
            "type": "bar",
            "spec": {
                "x": {"field": "region", "type": "nominal"},
                "y": {"field": "amount", "type": "quantitative"},
                "data": {
                    "columns": ["region", "amount"],
                    "rows": [],
                },
            },
        }
        assert validate_chart(spec) is None

    def test_validate_charts_accepts_list_of_chart_spec(self):
        specs: list[ChartSpec] = [
            {
                "type": "bar",
                "spec": {
                    "x": {"field": "region"},
                    "y": {"field": "amount"},
                    "data": {"columns": ["region", "amount"], "rows": []},
                },
            }
        ]
        kept, limitations = validate_charts(specs)  # type: ignore[arg-type]
        assert len(kept) == 1
        assert limitations == []

    def test_empty_result_extras_structure(self):
        """Verify that empty_result_extras output matches what pipeline expects."""
        extras = empty_result_extras()
        assert "charts" in extras
        assert "report" in extras
        assert isinstance(extras["charts"], list)
        assert extras["report"] is None
        # Must be JSON-serializable
        json.dumps(extras)