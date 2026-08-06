"""Unit tests for agent.nodes.pipeline — repair_hint integration.

Tests validate_sql and execute_sql produce correct repair_hint on failure
without changing the existing flow.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agent.nodes.pipeline import execute_sql, route_after_execute, route_after_validate, validate_sql


# ── validate_sql — repair_hint on gate failure ───────────────────────────

class TestValidateSqlRepairHint:
    """validate_sql must produce repair_hint on gate failure."""

    def test_gate_allowlist_failure(self, sample_ctx, sample_state):
        with patch(
            "agent.nodes.pipeline.validate_and_normalize_sql",
            return_value=MagicMock(
                ok=False,
                error="Table 'cte' is not in allowlist ['sales_wide']",
                sql=None,
            ),
        ):
            state = {**sample_state, "sql_draft": "SELECT * FROM sales_wide"}
            result = validate_sql(state, ctx=sample_ctx, sink=None)

        assert result["gate_ok"] is False
        assert result["gate_error"].startswith("[policy_allowlist]")
        assert result["repair_class"] == "policy_allowlist"
        assert result["repair_stage"] == "validate"
        hint = result["repair_hint"]
        assert hint is not None
        assert hint["repair_class"] == "policy_allowlist"
        assert "allowed tables" in hint["action"].lower()
        assert hint["is_repairable"] is True

    def test_gate_forbidden_keyword_failure(self, sample_ctx, sample_state):
        with patch(
            "agent.nodes.pipeline.validate_and_normalize_sql",
            return_value=MagicMock(
                ok=False,
                error="Forbidden keyword detected (DROP)",
                sql=None,
            ),
        ):
            state = {**sample_state, "sql_draft": "SELECT * FROM sales_wide"}
            result = validate_sql(state, ctx=sample_ctx, sink=None)

        assert result["gate_ok"] is False
        hint = result["repair_hint"]
        assert hint["repair_class"] == "policy_keyword"
        assert hint["is_repairable"] is False

    def test_gate_syntax_error(self, sample_ctx, sample_state):
        """'syntax error at or near' triggers engine_syntax, not policy_other."""
        with patch(
            "agent.nodes.pipeline.validate_and_normalize_sql",
            return_value=MagicMock(
                ok=False,
                error="syntax error at or near",
                sql=None,
            ),
        ):
            state = {**sample_state, "sql_draft": "SELECT * FROM sales_wide"}
            result = validate_sql(state, ctx=sample_ctx, sink=None)

        hint = result["repair_hint"]
        assert hint["repair_class"] == "engine_syntax"
        assert hint["is_repairable"] is True

    def test_gate_limit_missing(self, sample_ctx, sample_state):
        with patch(
            "agent.nodes.pipeline.validate_and_normalize_sql",
            return_value=MagicMock(
                ok=False,
                error="LIMIT is required but missing",
                sql=None,
            ),
        ):
            state = {**sample_state, "sql_draft": "SELECT * FROM sales_wide"}
            result = validate_sql(state, ctx=sample_ctx, sink=None)

        hint = result["repair_hint"]
        assert hint["repair_class"] == "policy_limit"
        assert hint["is_repairable"] is True

    def test_gate_unknown_error(self, sample_ctx, sample_state):
        """Message without any known keyword falls back to 'unknown'."""
        with patch(
            "agent.nodes.pipeline.validate_and_normalize_sql",
            return_value=MagicMock(
                ok=False,
                error="Rejected by internal check: code A7B9",
                sql=None,
            ),
        ):
            state = {**sample_state, "sql_draft": "SELECT * FROM sales_wide"}
            result = validate_sql(state, ctx=sample_ctx, sink=None)

        hint = result["repair_hint"]
        assert hint["repair_class"] == "unknown"
        assert hint["is_repairable"] is False

    def test_gate_success_no_repair_hint(self, sample_ctx, sample_state):
        """Normal flow: no repair_hint when gate passes."""
        with patch(
            "agent.nodes.pipeline.validate_and_normalize_sql",
            return_value=MagicMock(
                ok=True,
                error=None,
                sql="SELECT * FROM sales_wide",
            ),
        ):
            state = {**sample_state, "sql_draft": "SELECT * FROM sales_wide"}
            result = validate_sql(state, ctx=sample_ctx, sink=None)

        assert result["gate_ok"] is True
        assert result["sql_final"] == "SELECT * FROM sales_wide"
        assert result["gate_error"] == ""
        assert result.get("repair_hint") is None

    def test_retry_count_incremented_on_failure(self, sample_ctx, sample_state):
        with patch(
            "agent.nodes.pipeline.validate_and_normalize_sql",
            return_value=MagicMock(
                ok=False,
                error="Table not in allowlist",
                sql=None,
            ),
        ):
            state = {**sample_state, "sql_draft": "SELECT * FROM sales_wide", "retry_count": 1}
            result = validate_sql(state, ctx=sample_ctx, sink=None)

        assert result["retry_count"] == 2


# ── execute_sql — repair_hint on runtime failure ─────────────────────────

class TestExecuteSqlRepairHint:
    """execute_sql must produce repair_hint on runtime failure."""

    def test_execute_syntax_error(self, sample_ctx, sample_state):
        with patch(
            "agent.nodes.pipeline.checkpoint",
            return_value=None,
        ):
            ctx = sample_ctx
            ctx.execute_select = MagicMock(side_effect=Exception('Parser Error: syntax error at or near "FROM"'))
            state = {
                **sample_state,
                "sql_draft": "SELECT * FROM sales_wide",
                "sql_final": "SELECT * FROM",
            }
            result = execute_sql(state, ctx=ctx, sink=None)

        assert result["error"] != ""
        hint = result["repair_hint"]
        assert hint["repair_class"] == "engine_syntax"
        assert hint["is_repairable"] is True
        assert result["repair_class"] == "engine_syntax"
        assert result["repair_stage"] == "execute"

    def test_execute_runtime_error(self, sample_ctx, sample_state):
        with patch(
            "agent.nodes.pipeline.checkpoint",
            return_value=None,
        ):
            ctx = sample_ctx
            ctx.execute_select = MagicMock(side_effect=Exception("Division by zero"))
            state = {
                **sample_state,
                "sql_draft": "SELECT * FROM sales_wide",
                "sql_final": "SELECT 1/0",
            }
            result = execute_sql(state, ctx=ctx, sink=None)

        hint = result["repair_hint"]
        assert hint["repair_class"] == "engine_runtime"
        assert hint["is_repairable"] is True

    def test_execute_empty_result(self, sample_ctx, sample_state):
        with patch(
            "agent.nodes.pipeline.checkpoint",
            return_value=None,
        ):
            ctx = sample_ctx
            ctx.execute_select = MagicMock(side_effect=Exception("no rows returned"))
            state = {
                **sample_state,
                "sql_draft": "SELECT * FROM sales_wide",
                "sql_final": "SELECT * FROM sales_wide WHERE 1=0",
            }
            result = execute_sql(state, ctx=ctx, sink=None)

        hint = result["repair_hint"]
        assert hint["repair_class"] == "empty_result"
        assert hint["is_repairable"] is True

    def test_execute_retry_count_incremented(self, sample_ctx, sample_state):
        with patch(
            "agent.nodes.pipeline.checkpoint",
            return_value=None,
        ):
            ctx = sample_ctx
            ctx.execute_select = MagicMock(side_effect=Exception("Binder Error"))
            state = {
                **sample_state,
                "sql_draft": "SELECT * FROM sales_wide",
                "retry_count": 0,
            }
            result = execute_sql(state, ctx=ctx, sink=None)

        assert result["retry_count"] == 1
        assert result["gate_error"].startswith("[engine_runtime]")

    def test_execute_success_no_repair_hint(self, sample_ctx, sample_state):
        """Normal flow: no repair_hint when execute succeeds."""
        with patch(
            "agent.nodes.pipeline.checkpoint",
            return_value=None,
        ):
            ctx = sample_ctx
            ctx.execute_select = MagicMock(return_value={
                "columns": ["region"],
                "rows": [{"region": "North"}],
                "row_count": 1,
            })
            state = {
                **sample_state,
                "sql_draft": "SELECT * FROM sales_wide",
                "sql_final": "SELECT region FROM sales_wide",
            }
            result = execute_sql(state, ctx=ctx, sink=None)

        assert result["error"] == ""
        assert result.get("preview") is not None
        assert result.get("repair_hint") is None


# ── repair_history tracking ─────────────────────────────────────────────

class TestRepairHistoryValidateSql:
    """validate_sql must record repair_history on failure and success."""

    def test_first_failure_records_history(self, sample_ctx, sample_state):
        with patch(
            "agent.nodes.pipeline.validate_and_normalize_sql",
            return_value=MagicMock(
                ok=False,
                error="Table 'cte' is not in allowlist ['sales_wide']",
                sql=None,
            ),
        ):
            state = {**sample_state, "sql_draft": "SELECT * FROM sales_wide"}
            result = validate_sql(state, ctx=sample_ctx, sink=None)

        history = result.get("repair_history") or []
        assert len(history) == 1
        entry = history[0]
        assert entry["attempt"] == 1
        assert "sales_wide" in entry["sql_draft"]
        assert "not in allowlist" in entry["error"]
        assert entry["repair_class"] == "policy_allowlist"
        assert entry["is_repairable"] is True
        assert entry["gate_passed"] is False
        assert entry["stage"] == "validate_fail"

    def test_no_history_entry_on_first_success(self, sample_ctx, sample_state):
        """First success (no retry) should NOT add a success entry."""
        with patch(
            "agent.nodes.pipeline.validate_and_normalize_sql",
            return_value=MagicMock(
                ok=True,
                error=None,
                sql="SELECT * FROM sales_wide",
            ),
        ):
            state = {**sample_state, "sql_draft": "SELECT * FROM sales_wide"}
            result = validate_sql(state, ctx=sample_ctx, sink=None)

        history = result.get("repair_history") or []
        assert len(history) == 0

    def test_success_after_retry_records_history(self, sample_ctx, sample_state):
        """After a retry, validate_sql success appends a success entry."""
        with patch(
            "agent.nodes.pipeline.validate_and_normalize_sql",
            return_value=MagicMock(
                ok=True,
                error=None,
                sql="SELECT region FROM sales_wide",
            ),
        ):
            state = {
                **sample_state,
                "sql_draft": "SELECT * FROM sales_wide",
                "retry_count": 1,
                "repair_history": [{
                    "attempt": 1,
                    "sql_draft": "SELECT * FROM cte",
                    "error": "Table not in allowlist",
                    "repair_class": "policy_allowlist",
                    "is_repairable": True,
                    "gate_passed": False,
                    "stage": "validate_fail",
                }],
            }
            result = validate_sql(state, ctx=sample_ctx, sink=None)

        history = result.get("repair_history") or []
        assert len(history) == 2
        assert history[0]["gate_passed"] is False
        assert history[0]["stage"] == "validate_fail"
        assert history[1]["gate_passed"] is True
        assert history[1]["stage"] == "validate_ok"
        assert history[1]["attempt"] == 1
        assert history[1]["sql_final"] == "SELECT region FROM sales_wide"
        assert history[1]["sql_draft"] == "SELECT * FROM sales_wide"

    def test_multiple_failures_stack_history(self, sample_ctx, sample_state):
        """Each failure appends to history, preserving order."""
        with patch(
            "agent.nodes.pipeline.validate_and_normalize_sql",
            return_value=MagicMock(
                ok=False,
                error="LIMIT is required but missing",
                sql=None,
            ),
        ):
            state = {
                **sample_state,
                "sql_draft": "SELECT * FROM sales_wide",
                "retry_count": 1,
                "repair_history": [{
                    "attempt": 1,
                    "sql_draft": "SELECT * FROM cte",
                    "error": "Table not in allowlist",
                    "repair_class": "policy_allowlist",
                    "is_repairable": True,
                    "gate_passed": False,
                    "stage": "validate_fail",
                }],
            }
            result = validate_sql(state, ctx=sample_ctx, sink=None)

        history = result.get("repair_history") or []
        assert len(history) == 2
        assert history[1]["attempt"] == 2
        assert history[1]["repair_class"] == "policy_limit"


class TestRepairHistoryExecuteSql:
    """execute_sql must record repair_history on failure."""

    def test_execute_failure_records_history(self, sample_ctx, sample_state):
        with patch(
            "agent.nodes.pipeline.checkpoint",
            return_value=None,
        ):
            ctx = sample_ctx
            ctx.execute_select = MagicMock(side_effect=Exception("Division by zero"))
            state = {
                **sample_state,
                "sql_draft": "SELECT * FROM sales_wide",
                "sql_final": "SELECT 1/0",
            }
            result = execute_sql(state, ctx=ctx, sink=None)

        history = result.get("repair_history") or []
        assert len(history) == 1
        entry = history[0]
        assert entry["attempt"] == 1
        assert "SELECT 1/0" in entry["sql_draft"]
        assert "Division by zero" in entry["error"]
        assert entry["repair_class"] == "engine_runtime"
        assert entry["gate_passed"] is False
        assert entry["stage"] == "execute_fail"

    def test_execute_success_no_history(self, sample_ctx, sample_state):
        """First execute success (no retry) should not add history."""
        with patch(
            "agent.nodes.pipeline.checkpoint",
            return_value=None,
        ):
            ctx = sample_ctx
            ctx.execute_select = MagicMock(return_value={
                "columns": ["region"],
                "rows": [{"region": "North"}],
                "row_count": 1,
            })
            state = {
                **sample_state,
                "sql_draft": "SELECT * FROM sales_wide",
                "sql_final": "SELECT region FROM sales_wide",
            }
            result = execute_sql(state, ctx=ctx, sink=None)

        history = result.get("repair_history") or []
        assert len(history) == 0

    def test_history_preserves_existing_entries(self, sample_ctx, sample_state):
        """History should NOT delete or overwrite existing entries."""
        with patch(
            "agent.nodes.pipeline.checkpoint",
            return_value=None,
        ):
            ctx = sample_ctx
            ctx.execute_select = MagicMock(side_effect=Exception("Binder Error"))
            state = {
                **sample_state,
                "sql_draft": "SELECT * FROM sales_wide",
                "retry_count": 1,
                "sql_final": "SELECT * FROM nonexistent",
                "repair_history": [{
                    "attempt": 1,
                    "sql_draft": "SELECT * FROM cte",
                    "error": "Table not in allowlist",
                    "repair_class": "policy_allowlist",
                    "is_repairable": True,
                    "gate_passed": False,
                    "stage": "validate_fail",
                }],
            }
            result = execute_sql(state, ctx=ctx, sink=None)

        history = result.get("repair_history") or []
        assert len(history) == 2
        assert history[0]["repair_class"] == "policy_allowlist"
        assert history[1]["repair_class"] == "engine_runtime"

    def test_execute_success_after_retry_records_history(self, sample_ctx, sample_state):
        """After a retry, execute_sql success should record execute_ok."""
        with patch(
            "agent.nodes.pipeline.checkpoint",
            return_value=None,
        ):
            ctx = sample_ctx
            ctx.execute_select = MagicMock(return_value={
                "columns": ["region"],
                "rows": [{"region": "North"}],
                "row_count": 1,
            })
            state = {
                **sample_state,
                "sql_draft": "SELECT * FROM sales_wide",
                "retry_count": 1,
                "sql_final": "SELECT region FROM sales_wide",
                "repair_history": [{
                    "attempt": 1,
                    "sql_draft": "SELECT * FROM cte",
                    "error": "Table not in allowlist",
                    "repair_class": "policy_allowlist",
                    "is_repairable": True,
                    "gate_passed": False,
                    "stage": "validate_fail",
                }],
            }
            result = execute_sql(state, ctx=ctx, sink=None)

        history = result.get("repair_history") or []
        assert len(history) == 2
        assert history[1]["stage"] == "execute_ok"
        assert history[1]["gate_passed"] is True
        assert history[1]["sql_final"] == "SELECT region FROM sales_wide"


# ── Full mock repair flow ────────────────────────────────────────────────

class TestFullMockRepairFlow:
    """Simulate a complete repair cycle: Gate reject → retry → Gate pass."""

    def test_full_repair_flow_allowlist(self, sample_ctx, sample_state):
        """Simulate: bad SQL rejected → retry with good SQL → success."""
        with patch(
            "agent.nodes.pipeline.validate_and_normalize_sql",
        ) as mock_gate:
            mock_gate.side_effect = [
                MagicMock(
                    ok=False,
                    error="Table 'unauthorized_table' is not in allowlist ['sales_wide']",
                    sql=None,
                ),
                MagicMock(
                    ok=True,
                    error=None,
                    sql="SELECT * FROM sales_wide",
                ),
            ]

            state = {
                **sample_state,
                "sql_draft": "SELECT * FROM unauthorized_table",
            }

            # Step 1: validate_sql fails
            result1 = validate_sql(state, ctx=sample_ctx, sink=None)
            assert result1["gate_ok"] is False
            assert result1["repair_class"] == "policy_allowlist"
            assert result1["retry_count"] == 1
            history1 = result1["repair_history"]
            assert len(history1) == 1
            assert history1[0]["stage"] == "validate_fail"
            assert history1[0]["attempt"] == 1

            # Step 2: simulate LLM retry → generate new SQL
            result1["sql_draft"] = "SELECT * FROM sales_wide"

            # Step 3: validate_sql succeeds
            result2 = validate_sql(result1, ctx=sample_ctx, sink=None)
            assert result2["gate_ok"] is True
            assert result2["sql_final"] == "SELECT * FROM sales_wide"
            history2 = result2["repair_history"]
            assert len(history2) == 2
            assert history2[0]["stage"] == "validate_fail"
            assert history2[0]["gate_passed"] is False
            assert history2[1]["stage"] == "validate_ok"
            assert history2[1]["gate_passed"] is True
            assert history2[1]["sql_draft"] == "SELECT * FROM sales_wide"

    def test_full_repair_flow_limit_missing(self, sample_ctx, sample_state):
        """Simulate: missing LIMIT → retry with LIMIT → success."""
        with patch(
            "agent.nodes.pipeline.validate_and_normalize_sql",
        ) as mock_gate:
            mock_gate.side_effect = [
                MagicMock(
                    ok=False,
                    error="LIMIT is required but missing",
                    sql=None,
                ),
                MagicMock(
                    ok=True,
                    error=None,
                    sql="SELECT * FROM sales_wide LIMIT 200",
                ),
            ]

            state = {
                **sample_state,
                "sql_draft": "SELECT * FROM sales_wide",
            }

            result1 = validate_sql(state, ctx=sample_ctx, sink=None)
            assert result1["repair_class"] == "policy_limit"
            assert result1["retry_count"] == 1

            result1["sql_draft"] = "SELECT * FROM sales_wide LIMIT 200"
            result2 = validate_sql(result1, ctx=sample_ctx, sink=None)

            history = result2["repair_history"]
            assert len(history) == 2
            assert history[0]["repair_class"] == "policy_limit"
            assert history[1]["stage"] == "validate_ok"
            assert history[1]["gate_passed"] is True

    def test_full_repair_flow_non_repairable(self, sample_ctx, sample_state):
        """Simulate: DROP TABLE → non-repairable → routing stops at attempt 1."""
        with patch(
            "agent.nodes.pipeline.validate_and_normalize_sql",
        ) as mock_gate:
            mock_gate.side_effect = [
                MagicMock(
                    ok=False,
                    error="Forbidden keyword detected (DROP)",
                    sql=None,
                ),
            ]

            state = {
                **sample_state,
                "sql_draft": "DROP TABLE sales_wide",
            }

            r1 = validate_sql(state, ctx=sample_ctx, sink=None)
            assert r1["repair_class"] == "policy_keyword"
            assert r1["repair_hint"]["is_repairable"] is False
            assert len(r1["repair_history"]) == 1
            assert r1["retry_count"] == 1

            route = route_after_validate(r1)
            assert route == "fail", f"Expected 'fail' for non-repairable, got {route!r}"


class TestRepairHistoryEdgeCases:
    """Edge cases for repair_history."""

    def test_history_is_always_a_list(self, sample_ctx, sample_state):
        """Even with no failures, state.get('repair_history') should be list-like."""
        with patch(
            "agent.nodes.pipeline.validate_and_normalize_sql",
            return_value=MagicMock(
                ok=True,
                error=None,
                sql="SELECT * FROM sales_wide",
            ),
        ):
            state = {**sample_state, "sql_draft": "SELECT * FROM sales_wide"}
            result = validate_sql(state, ctx=sample_ctx, sink=None)

        assert isinstance(result.get("repair_history") or [], list)

    def test_history_entries_are_dicts(self, sample_ctx, sample_state):
        with patch(
            "agent.nodes.pipeline.validate_and_normalize_sql",
            return_value=MagicMock(
                ok=False,
                error="Rejected by internal check: code A7B9",
                sql=None,
            ),
        ):
            state = {**sample_state, "sql_draft": "SELECT * FROM sales_wide"}
            result = validate_sql(state, ctx=sample_ctx, sink=None)

        for entry in result.get("repair_history") or []:
            assert isinstance(entry, dict)
            assert "attempt" in entry
            assert "gate_passed" in entry


# ── Routing: is_repairable check ─────────────────────────────────────────

class TestRouteAfterValidateRepairable:
    """route_after_validate must check repair_hint.is_repairable."""

    def test_repairable_error_retries(self, sample_state):
        """policy_allowlist is repairable → return 'generate_sql'."""
        state = {
            **sample_state,
            "sql_draft": "SELECT * FROM sales_wide",
            "gate_ok": False,
            "retry_count": 0,
            "max_retries": 2,
            "repair_hint": {
                "repair_class": "policy_allowlist",
                "action": "Use allowed tables",
                "is_repairable": True,
            },
        }
        assert route_after_validate(state) == "generate_sql"

    def test_non_repairable_error_fails(self, sample_state):
        """policy_keyword is not repairable → return 'fail'."""
        state = {
            **sample_state,
            "sql_draft": "SELECT * FROM sales_wide",
            "gate_ok": False,
            "retry_count": 0,
            "max_retries": 2,
            "repair_hint": {
                "repair_class": "policy_keyword",
                "action": "Remove forbidden keywords",
                "is_repairable": False,
            },
        }
        assert route_after_validate(state) == "fail"

    def test_unknown_error_fails(self, sample_state):
        """unknown is not repairable → return 'fail'."""
        state = {
            **sample_state,
            "sql_draft": "SELECT * FROM sales_wide",
            "gate_ok": False,
            "retry_count": 0,
            "max_retries": 2,
            "repair_hint": {
                "repair_class": "unknown",
                "action": "Review error",
                "is_repairable": False,
            },
        }
        assert route_after_validate(state) == "fail"

    def test_gate_ok_skips_repairable_check(self, sample_state):
        """When gate passes, is_repairable is irrelevant."""
        state = {
            **sample_state,
            "sql_draft": "SELECT * FROM sales_wide",
            "gate_ok": True,
            "repair_hint": None,
        }
        assert route_after_validate(state) == "execute_sql"

    def test_max_retries_exceeded_for_repairable(self, sample_state):
        """Repairable but retry_count > max_retries → 'fail'."""
        state = {
            **sample_state,
            "sql_draft": "SELECT * FROM sales_wide",
            "gate_ok": False,
            "retry_count": 3,
            "max_retries": 2,
            "repair_hint": {
                "repair_class": "engine_syntax",
                "action": "Fix syntax",
                "is_repairable": True,
            },
        }
        assert route_after_validate(state) == "fail"

    def test_no_repair_hint_defaults_to_repairable(self, sample_state):
        """Missing repair_hint → treated as repairable (safe default)."""
        state = {
            **sample_state,
            "sql_draft": "SELECT * FROM sales_wide",
            "gate_ok": False,
            "retry_count": 0,
            "max_retries": 2,
        }
        assert route_after_validate(state) == "generate_sql"


class TestRouteAfterExecuteRepairable:
    """route_after_execute must check repair_hint.is_repairable."""

    def test_execute_success_skips_check(self, sample_state):
        state = {
            **sample_state,
            "sql_draft": "SELECT * FROM sales_wide",
            "preview": {"columns": ["x"], "rows": [], "row_count": 0},
            "error": "",
        }
        assert route_after_execute(state) == "summarize"

    def test_execute_repairable_error_retries(self, sample_state):
        state = {
            **sample_state,
            "sql_draft": "SELECT * FROM sales_wide",
            "preview": {},
            "error": "Division by zero",
            "retry_count": 0,
            "max_retries": 2,
            "repair_hint": {
                "repair_class": "engine_runtime",
                "action": "Fix runtime error",
                "is_repairable": True,
            },
        }
        assert route_after_execute(state) == "generate_sql"

    def test_execute_non_repairable_error_fails(self, sample_state):
        state = {
            **sample_state,
            "sql_draft": "SELECT * FROM sales_wide",
            "preview": {},
            "error": "Forbidden keyword",
            "retry_count": 0,
            "max_retries": 2,
            "repair_hint": {
                "repair_class": "policy_keyword",
                "action": "Remove forbidden keywords",
                "is_repairable": False,
            },
        }
        assert route_after_execute(state) == "fail"