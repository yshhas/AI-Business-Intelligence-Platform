"""Unit tests for agent.report — determinisitc report builder.

Tests cover template report generation, markdown formatting,
chart/limitation pass-through, and LLM degradation fallback.
No LLM / database dependencies.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from agent.report import _template_report, build_report


# ── build_report ─────────────────────────────────────────────────────────

class TestBuildReport:
    """Main entry point: returns ReportDoc with title/markdown/sections."""

    def test_empty_preview(self, make_preview):
        report = build_report(
            question="Show sales",
            summary="",
            sql="SELECT * FROM t",
            preview=make_preview([], []),
            charts=[],
            limitations=[],
        )
        assert report["title"] == "分析简报"
        assert "结果行数：0" in report["markdown"]
        assert len(report["sections"]) == 3

    def test_normal_report_all_sections(self, make_preview):
        report = build_report(
            question="Show sales by region",
            summary="East leads with 500.",
            sql="SELECT region, SUM(amount) FROM sales_wide GROUP BY region",
            preview=make_preview(
                ["region", "total"],
                [{"region": "East", "total": 500}],
            ),
            charts=[],
            limitations=["DuckDB in-memory"],
        )
        assert report["title"] == "分析简报"
        assert "East leads" in report["markdown"]
        assert "DuckDB" in report["markdown"]
        sections = report["sections"]
        assert sections[0]["heading"] == "结论"
        assert sections[1]["heading"] == "关键发现"
        assert sections[2]["heading"] == "局限与下一步"

    def test_markdown_starts_with_headings(self, make_preview):
        report = build_report(
            question="Q",
            summary="Summary.",
            sql="SELECT 1",
            preview=make_preview(["x"], [{"x": 1}]),
            charts=[],
            limitations=[],
        )
        assert report["markdown"].startswith("## 结论")

    def test_chart_titles_in_report(self, make_preview):
        charts = [
            {"id": "c1", "title": "Sales by Region", "type": "bar"},
            {"id": "c2", "title": "Revenue Trend", "type": "line"},
        ]
        report = build_report(
            question="Q",
            summary="S",
            sql="SELECT 1",
            preview=make_preview(["x"], [{"x": 1}]),
            charts=charts,
            limitations=[],
        )
        assert "Sales by Region" in report["markdown"]
        assert "Revenue Trend" in report["markdown"]

    def test_no_charts_shows_fallback_text(self, make_preview):
        report = build_report(
            question="Q",
            summary="S",
            sql="SELECT 1",
            preview=make_preview(["x"], [{"x": 1}]),
            charts=[],
            limitations=[],
        )
        assert "本次未生成图表" in report["markdown"]

    def test_limitations_in_report(self, make_preview):
        report = build_report(
            question="Q",
            summary="S",
            sql="SELECT 1",
            preview=make_preview(["x"], [{"x": 1}]),
            charts=[],
            limitations=["DuckDB in-memory", "SQL Gate enforced"],
        )
        assert "DuckDB in-memory" in report["markdown"]
        assert "SQL Gate enforced" in report["markdown"]

    def test_no_limitations_shows_fallback(self, make_preview):
        report = build_report(
            question="Q",
            summary="S",
            sql="SELECT 1",
            preview=make_preview(["x"], [{"x": 1}]),
            charts=[],
            limitations=[],
        )
        assert "无额外局限说明" in report["markdown"]

    def test_llm_fallback_to_template(self, make_preview):
        llm_fn = MagicMock(side_effect=RuntimeError("fail"))
        report = build_report(
            question="Q",
            summary="S",
            sql="SELECT 1",
            preview=make_preview(["x"], [{"x": 1}]),
            charts=[],
            limitations=[],
            llm_fn=llm_fn,
        )
        # Should fallback to template, not raise
        assert report["title"] == "分析简报"
        assert "## 结论" in report["markdown"]

    def test_llm_empty_response_fallback(self, make_preview):
        llm_fn = MagicMock(return_value="")
        report = build_report(
            question="Q",
            summary="S",
            sql="SELECT 1",
            preview=make_preview(["x"], [{"x": 1}]),
            charts=[],
            limitations=[],
            llm_fn=llm_fn,
        )
        assert "## 结论" in report["markdown"]

    def test_llm_success_uses_llm_output(self, make_preview):
        llm_fn = MagicMock(return_value="**LLM generated** report content.")
        report = build_report(
            question="Q",
            summary="S",
            sql="SELECT 1",
            preview=make_preview(["x"], [{"x": 1}]),
            charts=[],
            limitations=[],
            llm_fn=llm_fn,
        )
        assert "**LLM generated**" in report["markdown"]

    def test_non_list_rows_handles_gracefully(self):
        report = build_report(
            question="Q",
            summary="S",
            sql="SELECT 1",
            preview={"columns": ["x"], "rows": "not a list"},
            charts=[],
            limitations=[],
        )
        assert "结果行数：0" in report["markdown"]

    def test_sql_truncated_in_key_findings(self, make_preview):
        long_sql = "SELECT " + ", ".join([f"column_{i}" for i in range(100)])
        report = build_report(
            question="Q",
            summary="S",
            sql=long_sql,
            preview=make_preview(["x"], [{"x": 1}]),
            charts=[],
            limitations=[],
        )
        # SQL longer than 800 chars should be truncated in report
        sql_in_report = report["markdown"]
        assert len(long_sql) > 800
        assert long_sql[:200] in sql_in_report


# ── _template_report ─────────────────────────────────────────────────────

class TestTemplateReport:
    """Fallback template report structure."""

    def test_all_sections_present(self):
        report = _template_report(
            question="Show sales",
            summary="Sales are up.",
            sql="SELECT * FROM t",
            row_count=42,
            columns=["region", "amount"],
            chart_titles=["Sales by Region"],
            limitations=["DuckDB"],
        )
        assert len(report["sections"]) == 3
        assert report["title"] == "分析简报"

    def test_markdown_sections_separated(self):
        report = _template_report(
            question="Q", summary="S", sql="SELECT 1",
            row_count=1, columns=["x"], chart_titles=[], limitations=[],
        )
        md = report["markdown"]
        assert md.startswith("## 结论")
        assert "## 关键发现" in md
        assert "## 局限与下一步" in md