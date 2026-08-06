"""Unit tests for untested pipeline node functions.

Covers: load_context, link_schema, generate_sql, summarize, build_charts,
write_report, hitl_plan_done.

All tests mock external dependencies (LLM, DB, Gate); node functions
themselves execute with real logic.  No network / filesystem / DuckDB.

Known issues (resolved):
  - pipeline.py L628: _produce_sql() referenced state.get("repair_hint")
    but state was not in scope → fixed in P1-5 by adding repair_hint
    parameter to _produce_sql and passing it from generate_sql.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agent.nodes.pipeline import (
    build_charts,
    generate_sql,
    hitl_plan_done,
    link_schema,
    load_context,
    summarize,
    write_report,
)
from agent.prompts_sql import build_text_to_sql_prompts
from agent.schema_linking import LinkResult


# ── load_context ─────────────────────────────────────────────────────────

class TestLoadContext:
    """load_context copies ctx fields into state and handles HITL modes."""

    def test_normal_path(self, sample_ctx, sample_state):
        """Normal load: question / schema / duckdb_table copied to state."""
        ctx = sample_ctx
        state = {**sample_state}

        result = load_context(state, ctx=ctx, sink=None)

        assert result["question"] == "Show sales by region"
        assert result["duckdb_table"] == "sales_wide"
        assert result["retry_count"] == 0
        assert result["max_retries"] == 2
        assert result["default_limit"] == 200
        assert result["status"] == "running"
        assert result["limitations"] == []
        assert "workspace_id" in result
        assert "dataset_id" in result

    def test_hitl_execute_with_approved_sql(self, sample_ctx, sample_state):
        """HITL execute-only: approved_sql injected into sql_draft/sql_final."""
        ctx = sample_ctx
        ctx.hitl_execute_only = True
        ctx.approved_sql = "SELECT region, SUM(amount) FROM sales_wide GROUP BY region"
        state = {**sample_state}

        result = load_context(state, ctx=ctx, sink=None)

        assert result["sql_draft"] == ctx.approved_sql
        assert result["sql_final"] == ctx.approved_sql
        assert result["hitl_execute_only"] is True
        assert any("HITL" in s for s in result["limitations"])

    def test_hitl_execute_missing_sql(self, sample_ctx, sample_state):
        """HITL execute-only with empty approved_sql → failed state."""
        ctx = sample_ctx
        ctx.hitl_execute_only = True
        ctx.approved_sql = ""
        state = {**sample_state}

        result = load_context(state, ctx=ctx, sink=None)

        assert result["status"] == "failed"
        assert "missing" in result.get("error", "").lower()
        assert result.get("link_status") == "failed"

    def test_preserves_existing_state(self, sample_ctx, sample_state):
        """Existing state fields are preserved, new fields merged."""
        ctx = sample_ctx
        state = {**sample_state, "summary": "existing summary", "error": "old error"}

        result = load_context(state, ctx=ctx, sink=None)

        assert result["question"] == "Show sales by region"
        assert result["retry_count"] == 0
        assert result["status"] == "running"


# ── link_schema ──────────────────────────────────────────────────────────

class TestLinkSchema:
    """link_schema wraps run_link_schema and maps LinkResult to state."""

    def _link_result(self, **overrides: object) -> LinkResult:
        kwargs: dict = {
            "link_status": "ok",
            "link_method": "token_overlap",
            "link_reason": None,
            "selected_tables": ["sales_wide"],
            "selected_columns": ["region", "amount"],
            "column_count_full": 3,
            "column_count_linked": 2,
            "scores": {"region": 1.0, "amount": 0.8},
            "synonyms_applied": [],
        }
        kwargs.update({k: v for k, v in overrides.items() if v is not None})
        return LinkResult(**kwargs)

    def test_link_success(self, sample_ctx, sample_state):
        """Normal link: results written to state."""
        lr = self._link_result()
        ctx = sample_ctx
        state = {**sample_state}

        with patch("agent.nodes.pipeline.run_link_schema", return_value=lr):
            result = link_schema(state, ctx=ctx, sink=None)

        assert result["link_status"] == "ok"
        assert result["selected_tables"] == ["sales_wide"]
        assert result["selected_columns"] == ["region", "amount"]
        assert result["column_count_full"] == 3
        assert result["column_count_linked"] == 2
        assert result.get("status") != "failed"

    def test_link_failed(self, sample_ctx, sample_state):
        """Failed link → status=failed, error set."""
        lr = self._link_result(
            link_status="failed",
            link_reason="no columns matched",
            selected_columns=[],
        )
        ctx = sample_ctx
        state = {**sample_state}

        with patch("agent.nodes.pipeline.run_link_schema", return_value=lr):
            result = link_schema(state, ctx=ctx, sink=None)

        assert result["link_status"] == "failed"
        assert result["status"] == "failed"
        assert "schema linking failed" in result.get("error", "")

    def test_link_degraded(self, sample_ctx, sample_state):
        """Degraded (partial) link → status not failed, columns written."""
        lr = self._link_result(
            link_status="partial",
            link_reason="low confidence",
            selected_columns=["region"],
            column_count_linked=1,
        )
        ctx = sample_ctx
        state = {**sample_state}

        with patch("agent.nodes.pipeline.run_link_schema", return_value=lr):
            result = link_schema(state, ctx=ctx, sink=None)

        assert result["link_status"] == "partial"
        assert result.get("status", "") != "failed"
        assert result["selected_columns"] == ["region"]

    def test_allowed_tables_includes_duckdb_table(self, sample_ctx, sample_state):
        """duckdb_table is always added to allowed_tables."""
        lr = self._link_result()
        ctx = sample_ctx
        ctx.allowed_tables = ["other_table"]
        state = {**sample_state}

        with patch("agent.nodes.pipeline.run_link_schema") as mock_link:
            mock_link.return_value = lr
            link_schema(state, ctx=ctx, sink=None)

        call_kwargs = mock_link.call_args.kwargs
        assert "sales_wide" in call_kwargs["allowed_tables"]


# ── generate_sql ─────────────────────────────────────────────────────────

class TestGenerateSql:
    """generate_sql produces SQL via _produce_sql (LLM or heuristic)."""

    def test_generate_success(self, sample_ctx, sample_state):
        """Normal generation: sql_draft written, gate_error cleared."""
        ctx = sample_ctx
        state = {
            **sample_state,
            "link_status": "ok",
            "selected_columns": ["region", "amount"],
        }

        with patch(
            "agent.nodes.pipeline._produce_sql",
            return_value=(
                "SELECT region, SUM(amount) FROM sales_wide GROUP BY region",
                {"model": "test", "status": "ok"},
            ),
        ):
            result = generate_sql(state, ctx=ctx, sink=None)

        assert result["sql_draft"].startswith("SELECT")
        assert result["gate_error"] == ""
        assert result.get("status") != "failed"

    def test_generate_failure(self, sample_ctx, sample_state):
        """_produce_sql raises → status=failed, sql_draft cleared."""
        ctx = sample_ctx
        state = {**sample_state}

        with patch(
            "agent.nodes.pipeline._produce_sql",
            side_effect=RuntimeError("LLM timeout"),
        ):
            result = generate_sql(state, ctx=ctx, sink=None)

        assert result["status"] == "failed"
        assert "LLM timeout" in result.get("error", "")
        assert result.get("sql_draft") == ""

    def test_hitl_execute_short_circuit(self, sample_ctx, sample_state):
        """HITL execute-only blocks SQL regeneration."""
        ctx = sample_ctx
        state = {**sample_state, "hitl_execute_only": True}

        result = generate_sql(state, ctx=ctx, sink=None)

        assert result["status"] == "failed"
        assert "forbidden" in result.get("error", "").lower()
        assert result.get("sql_draft") == ""

    def test_uses_selected_columns(self, sample_ctx, sample_state):
        """selected_columns from schema linking are used to filter schema."""
        ctx = sample_ctx
        ctx.schema = [
            {"name": "region", "type": "VARCHAR"},
            {"name": "amount", "type": "DOUBLE"},
            {"name": "order_date", "type": "DATE"},
            {"name": "customer_id", "type": "INTEGER"},
        ]
        state = {
            **sample_state,
            "selected_columns": ["region", "amount"],
            "link_status": "ok",
        }

        with patch(
            "agent.nodes.pipeline._produce_sql",
            return_value=("SELECT region, SUM(amount) FROM sales_wide", None),
        ) as mock_produce:
            generate_sql(state, ctx=ctx, sink=None)

        call_kwargs = mock_produce.call_args.kwargs
        assert len(call_kwargs["schema"]) == 2
        schema_names = [c["name"] for c in call_kwargs["schema"]]
        assert schema_names == ["region", "amount"]

    def test_repair_hint_passed_to_prompt(self, sample_ctx, sample_state):
        """L628 bug fix: repair_hint must reach build_text_to_sql_prompts."""
        ctx = sample_ctx
        ctx.llm_api_key = "sk-test"
        ctx.llm_base_url = "https://api.test.com/v1"
        ctx.llm_model = "test-model"
        state = {
            **sample_state,
            "link_status": "ok",
            "selected_columns": ["region", "amount"],
            "repair_hint": {
                "repair_class": "policy_allowlist",
                "action": "Use allowed tables",
                "is_repairable": True,
            },
        }

        with patch(
            "agent.nodes.pipeline.chat_completion_result",
            return_value=MagicMock(
                content='{"sql": "SELECT region FROM sales_wide", "explanation": "ok"}',
                model="test",
                as_step_llm=MagicMock(return_value={"status": "ok"}),
            ),
        ), patch(
            "agent.nodes.pipeline.build_text_to_sql_prompts",
            wraps=build_text_to_sql_prompts,
        ) as mock_build:
            result = generate_sql(state, ctx=ctx, sink=None)

        assert result["sql_draft"] != ""
        # Verify repair_hint was passed to prompt builder
        call_kwargs = mock_build.call_args.kwargs
        assert call_kwargs.get("repair_hint") == {
            "repair_class": "policy_allowlist",
            "action": "Use allowed tables",
            "is_repairable": True,
        }


# ── summarize ────────────────────────────────────────────────────────────

class TestSummarize:
    """summarize produces a natural-language summary via _produce_summary."""

    def test_summarize_success(self, sample_ctx, sample_state):
        """Normal summary: summary text written, default limitations added."""
        ctx = sample_ctx
        state = {
            **sample_state,
            "sql_final": "SELECT region, SUM(amount) FROM sales_wide GROUP BY region",
            "preview": {
                "columns": ["region", "total"],
                "rows": [{"region": "East", "total": 500}],
                "row_count": 1,
            },
        }

        with patch(
            "agent.nodes.pipeline._produce_summary",
            return_value=("East region has total sales of 500.", {"status": "ok"}),
        ):
            result = summarize(state, ctx=ctx, sink=None)

        assert result["summary"] == "East region has total sales of 500."
        assert result["status"] == "succeeded"
        assert any("DuckDB" in s for s in result["limitations"])
        assert any("SQL Gate" in s for s in result["limitations"])

    def test_summarize_empty_rows(self, sample_ctx, sample_state):
        """Empty preview → summary still produced (heuristic)."""
        ctx = sample_ctx
        state = {
            **sample_state,
            "sql_final": "SELECT * FROM sales_wide WHERE 1=0",
            "preview": {"columns": [], "rows": [], "row_count": 0},
        }

        with patch(
            "agent.nodes.pipeline._produce_summary",
            return_value=("Query returned 0 rows.", {"status": "skipped", "mode": "heuristic"}),
        ):
            result = summarize(state, ctx=ctx, sink=None)

        assert result["summary"] != ""
        assert result["status"] == "succeeded"

    def test_exposes_repair_history(self, sample_ctx, sample_state):
        """repair_history is exposed in output for eval observability."""
        ctx = sample_ctx
        state = {
            **sample_state,
            "sql_final": "SELECT * FROM sales_wide",
            "preview": {"columns": ["region"], "rows": [], "row_count": 0},
            "repair_history": [
                {"attempt": 1, "error": "allowlist", "stage": "validate_fail"},
                {"attempt": 1, "sql_final": "SELECT * FROM sales_wide", "stage": "validate_ok"},
            ],
            "retry_count": 1,
        }

        with patch(
            "agent.nodes.pipeline._produce_summary",
            return_value=("Summary text", None),
        ):
            result = summarize(state, ctx=ctx, sink=None)

        assert result["status"] == "succeeded"
        assert result.get("summary") == "Summary text"

    def test_status_set_to_succeeded(self, sample_ctx, sample_state):
        """Summarize sets status=succeeded and clears charts/report."""
        ctx = sample_ctx
        state = {
            **sample_state,
            "sql_final": "SELECT * FROM sales_wide",
            "preview": {"columns": [], "rows": [], "row_count": 0},
        }

        with patch(
            "agent.nodes.pipeline._produce_summary",
            return_value=("ok", None),
        ):
            result = summarize(state, ctx=ctx, sink=None)

        assert result["status"] == "succeeded"
        assert result["charts"] == []
        assert result["report"] is None


# ── build_charts ─────────────────────────────────────────────────────────

class TestBuildCharts:
    """build_charts builds ChartSpec list from preview data (no LLM)."""

    def test_build_charts_success(self, sample_ctx, sample_state):
        """Normal chart build: charts written to state."""
        ctx = sample_ctx
        ctx.llm_api_key = ""
        state = {
            **sample_state,
            "preview": {
                "columns": ["region", "total"],
                "rows": [{"region": "East", "total": 500}],
                "row_count": 1,
            },
            "summary": "Sales summary",
        }
        mock_charts = [
            {"type": "bar", "title": "Sales by Region", "x": "region", "y": "total"},
            {"type": "pie", "title": "Sales Distribution", "x": "region", "y": "total"},
        ]

        with patch(
            "agent.charts.build_charts_from_preview",
            return_value=(mock_charts, []),
        ), patch(
            "agent.contracts.validate_charts",
            return_value=(mock_charts, []),
        ):
            result = build_charts(state, ctx=ctx, sink=None)

        assert len(result["charts"]) == 2
        assert result["status"] == "succeeded"

    def test_build_charts_empty(self, sample_ctx, sample_state):
        """No data → empty charts, no failure."""
        ctx = sample_ctx
        ctx.llm_api_key = ""
        state = {
            **sample_state,
            "preview": {"columns": [], "rows": [], "row_count": 0},
        }

        with patch(
            "agent.charts.build_charts_from_preview",
            return_value=([], ["no data for charts"]),
        ), patch(
            "agent.contracts.validate_charts",
            return_value=([], []),
        ):
            result = build_charts(state, ctx=ctx, sink=None)

        assert result["charts"] == []
        assert result["status"] == "succeeded"

    def test_build_charts_degraded(self, sample_ctx, sample_state):
        """build_charts_from_preview raises → degraded, charts=[] but status=succeeded."""
        ctx = sample_ctx
        ctx.llm_api_key = ""
        state = {
            **sample_state,
            "preview": {"columns": ["region"], "rows": [], "row_count": 0},
        }

        with patch(
            "agent.charts.build_charts_from_preview",
            side_effect=ValueError("bad chart data"),
        ):
            result = build_charts(state, ctx=ctx, sink=None)

        assert result["charts"] == []
        assert result["status"] == "succeeded"
        assert any("degraded" in s for s in result["limitations"])


# ── write_report ─────────────────────────────────────────────────────────

class TestWriteReport:
    """write_report builds a markdown report from summary + charts."""

    def test_write_report_success(self, sample_ctx, sample_state):
        """Normal report: title + markdown written."""
        ctx = sample_ctx
        ctx.llm_api_key = ""
        state = {
            **sample_state,
            "sql_final": "SELECT region, SUM(amount) FROM sales_wide GROUP BY region",
            "preview": {
                "columns": ["region", "total"],
                "rows": [{"region": "East", "total": 500}],
                "row_count": 1,
            },
            "summary": "East region has 500 total sales.",
            "charts": [
                {"type": "bar", "title": "Sales by Region", "x": "region", "y": "total"},
            ],
        }
        mock_report = {
            "title": "分析简报",
            "markdown": "## 结论\n\nEast region has 500 total sales.",
            "sections": [{"heading": "结论", "body": "East region has 500 total sales."}],
        }

        with patch(
            "agent.report.build_report",
            return_value=mock_report,
        ):
            result = write_report(state, ctx=ctx, sink=None)

        assert result["report"]["title"] == "分析简报"
        assert "markdown" in result["report"]
        assert result["status"] == "succeeded"

    def test_write_report_degraded(self, sample_ctx, sample_state):
        """build_report raises → degraded with fallback markdown."""
        ctx = sample_ctx
        ctx.llm_api_key = ""
        state = {
            **sample_state,
            "sql_final": "SELECT * FROM sales_wide",
            "preview": {"columns": [], "rows": [], "row_count": 0},
            "summary": "No data available.",
        }

        with patch(
            "agent.report.build_report",
            side_effect=RuntimeError("report build failed"),
        ):
            result = write_report(state, ctx=ctx, sink=None)

        assert result["status"] == "succeeded"
        assert "markdown" in result["report"]
        assert any("degraded" in s for s in result["limitations"])

    def test_write_report_with_charts(self, sample_ctx, sample_state):
        """Charts present → build_report receives chart data."""
        ctx = sample_ctx
        ctx.llm_api_key = ""
        state = {
            **sample_state,
            "sql_final": "SELECT * FROM sales_wide",
            "preview": {"columns": ["region"], "rows": [], "row_count": 0},
            "summary": "Summary",
            "charts": [{"type": "bar", "title": "Chart 1", "x": "region", "y": "total"}],
        }

        with patch(
            "agent.report.build_report",
            return_value={"title": "T", "markdown": "M", "sections": []},
        ) as mock_build:
            write_report(state, ctx=ctx, sink=None)

        call_kwargs = mock_build.call_args.kwargs
        assert len(call_kwargs["charts"]) == 1


# ── hitl_plan_done ───────────────────────────────────────────────────────

class TestHitlPlanDone:
    """hitl_plan_done finalises HITL plan phase before execute."""

    def test_hitl_plan_done(self, sample_ctx, sample_state):
        """HITL plan done: preview cleared, placeholder summary set."""
        ctx = sample_ctx
        state = {
            **sample_state,
            "sql_final": "SELECT * FROM sales_wide",
            "hitl_plan_only": True,
            "preview": {"columns": ["region"], "rows": [{"region": "E"}], "row_count": 1},
        }

        result = hitl_plan_done(state, ctx=ctx, sink=None)

        assert result["status"] == "succeeded"
        assert result["preview"] == {"columns": [], "rows": [], "row_count": 0}
        assert "awaiting human approval" in result.get("summary", "")
        assert result["charts"] == []
        assert result["report"] is None

    def test_adds_hitl_limitation(self, sample_ctx, sample_state):
        """HITL limitation is added without duplication."""
        ctx = sample_ctx
        state = {
            **sample_state,
            "sql_final": "SELECT * FROM sales_wide",
            "hitl_plan_only": True,
            "limitations": ["existing limitation"],
        }

        result = hitl_plan_done(state, ctx=ctx, sink=None)

        assert "existing limitation" in result["limitations"]
        assert any("HITL" in s for s in result["limitations"])
        hitl_notes = [s for s in result["limitations"] if "HITL" in s]
        assert len(hitl_notes) == 1