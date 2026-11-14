"""Unit tests for agent.kernel.policies — Policy wrappers over SQL Gate.

Tests verify apply_sql_select_gate correctly bridges GateResult to
PolicyDecision, forwarding parameters and preserving error information.
All tests mock validate_and_normalize_sql to isolate the wrapper logic.
"""

from __future__ import annotations

from unittest.mock import patch

from agent.gates.sql_gate import GateResult
from agent.kernel.policies import POLICY_SQL_SELECT_GATE, apply_sql_select_gate


# ── apply_sql_select_gate — normal path ──────────────────────────────────

class TestApplySqlSelectGatePass:
    """Gate passes → PolicyDecision.ok=True, reason=None."""

    def test_simple_select_passes(self):
        """Valid SELECT passes gate, decision reflects success."""
        with patch(
            "agent.kernel.policies.validate_and_normalize_sql",
            return_value=GateResult(
                ok=True, error=None, sql="SELECT 1",
            ),
        ):
            gate, decision = apply_sql_select_gate(
                "SELECT 1",
                allowed_tables={"t"},
            )

        assert gate.ok is True
        assert decision.ok is True
        assert decision.reason is None
        assert decision.policy_id == POLICY_SQL_SELECT_GATE
        assert decision.tool_id == "sql.execute_select"

    def test_select_with_join_passes(self):
        """Multi-table SELECT passes when all tables are in allowlist."""
        with patch(
            "agent.kernel.policies.validate_and_normalize_sql",
            return_value=GateResult(
                ok=True, error=None, sql="SELECT a.x, b.y FROM a JOIN b ON a.id=b.id",
            ),
        ):
            _, decision = apply_sql_select_gate(
                "SELECT a.x, b.y FROM a JOIN b ON a.id=b.id",
                allowed_tables={"a", "b"},
            )

        assert decision.ok is True
        assert decision.reason is None


# ── apply_sql_select_gate — reject paths ─────────────────────────────────

class TestApplySqlSelectGateReject:
    """Gate rejects → PolicyDecision.ok=False, reason=error message."""

    def test_table_not_in_allowlist(self):
        """Table not in allowlist → reject with error message."""
        error_msg = "Table 'unauthorized' is not in allowlist ['sales_wide']"
        with patch(
            "agent.kernel.policies.validate_and_normalize_sql",
            return_value=GateResult(ok=False, error=error_msg, sql=None),
        ):
            _, decision = apply_sql_select_gate(
                "SELECT * FROM unauthorized",
                allowed_tables={"sales_wide"},
            )

        assert decision.ok is False
        assert error_msg in decision.reason
        assert decision.policy_id == POLICY_SQL_SELECT_GATE

    def test_forbidden_keyword(self):
        """DROP/DELETE/INSERT keywords → reject."""
        error_msg = "Forbidden keyword detected (DROP)"
        with patch(
            "agent.kernel.policies.validate_and_normalize_sql",
            return_value=GateResult(ok=False, error=error_msg, sql=None),
        ):
            _, decision = apply_sql_select_gate(
                "DROP TABLE t",
                allowed_tables={"t"},
            )

        assert decision.ok is False
        assert "DROP" in decision.reason

    def test_missing_limit(self):
        """LIMIT is required → reject."""
        error_msg = "LIMIT is required but missing"
        with patch(
            "agent.kernel.policies.validate_and_normalize_sql",
            return_value=GateResult(ok=False, error=error_msg, sql=None),
        ):
            _, decision = apply_sql_select_gate(
                "SELECT * FROM t",
                allowed_tables={"t"},
            )

        assert decision.ok is False
        assert "LIMIT" in decision.reason

    def test_syntax_error(self):
        """Syntax error → reject with error message."""
        error_msg = "syntax error at or near 'FRO'"
        with patch(
            "agent.kernel.policies.validate_and_normalize_sql",
            return_value=GateResult(ok=False, error=error_msg, sql=None),
        ):
            _, decision = apply_sql_select_gate(
                "SELECT * FRO t",
                allowed_tables={"t"},
            )

        assert decision.ok is False
        assert "syntax error" in decision.reason

    def test_reason_is_none_when_gate_error_is_none(self):
        """Even when ok=False, if error=None, reason stays None."""
        with patch(
            "agent.kernel.policies.validate_and_normalize_sql",
            return_value=GateResult(ok=False, error=None, sql=None),
        ):
            _, decision = apply_sql_select_gate(
                "SELECT * FROM t",
                allowed_tables={"t"},
            )

        assert decision.ok is False
        assert decision.reason is None


# ── apply_sql_select_gate — parameter forwarding ─────────────────────────

class TestApplySqlSelectGateParameterForwarding:
    """Verify parameters are correctly forwarded to validate_and_normalize_sql."""

    def test_allowed_tables_forwarded(self):
        """allowed_tables set is passed to the gate."""
        with patch(
            "agent.kernel.policies.validate_and_normalize_sql",
            return_value=GateResult(ok=True, error=None, sql="SELECT 1"),
        ) as mock_gate:
            apply_sql_select_gate(
                "SELECT 1",
                allowed_tables={"sales_wide", "orders"},
            )

        call_kwargs = mock_gate.call_args.kwargs
        assert call_kwargs["allowed_tables"] == {"sales_wide", "orders"}

    def test_default_limit_forwarded(self):
        """default_limit is passed to the gate."""
        with patch(
            "agent.kernel.policies.validate_and_normalize_sql",
            return_value=GateResult(ok=True, error=None, sql="SELECT 1"),
        ) as mock_gate:
            apply_sql_select_gate(
                "SELECT 1",
                allowed_tables={"t"},
                default_limit=500,
            )

        call_kwargs = mock_gate.call_args.kwargs
        assert call_kwargs["default_limit"] == 500

    def test_default_limit_uses_default(self):
        """When not specified, default_limit defaults to 200."""
        with patch(
            "agent.kernel.policies.validate_and_normalize_sql",
            return_value=GateResult(ok=True, error=None, sql="SELECT 1"),
        ) as mock_gate:
            apply_sql_select_gate(
                "SELECT 1",
                allowed_tables={"t"},
            )

        call_kwargs = mock_gate.call_args.kwargs
        assert call_kwargs["default_limit"] == 200

    def test_sql_forwarded_as_is(self):
        """SQL string is forwarded unchanged."""
        with patch(
            "agent.kernel.policies.validate_and_normalize_sql",
            return_value=GateResult(ok=True, error=None, sql="SELECT 1"),
        ) as mock_gate:
            apply_sql_select_gate(
                "SELECT a, b FROM t WHERE x > 0 LIMIT 10",
                allowed_tables={"t"},
            )

        call_args = mock_gate.call_args.args
        assert call_args[0] == "SELECT a, b FROM t WHERE x > 0 LIMIT 10"


# ── apply_sql_select_gate — edge cases ───────────────────────────────────

class TestApplySqlSelectGateEdgeCases:
    """Boundary and edge behavior for the wrapper."""

    def test_empty_sql(self):
        """Empty SQL is forwarded to gate (gate handles validation)."""
        with patch(
            "agent.kernel.policies.validate_and_normalize_sql",
            return_value=GateResult(ok=False, error="Empty SQL", sql=None),
        ):
            _, decision = apply_sql_select_gate(
                "",
                allowed_tables={"t"},
            )

        assert decision.ok is False
        assert decision.reason == "Empty SQL"

    def test_empty_allowed_tables(self):
        """Empty allowed_tables set is forwarded; gate decides."""
        with patch(
            "agent.kernel.policies.validate_and_normalize_sql",
            return_value=GateResult(ok=False, error="No tables allowed", sql=None),
        ):
            _, decision = apply_sql_select_gate(
                "SELECT 1",
                allowed_tables=set(),
            )

        assert decision.ok is False

    def test_default_limit_zero(self):
        """default_limit=0 is forwarded; gate decides if valid."""
        with patch(
            "agent.kernel.policies.validate_and_normalize_sql",
            return_value=GateResult(ok=True, error=None, sql="SELECT 1"),
        ) as mock_gate:
            apply_sql_select_gate(
                "SELECT 1",
                allowed_tables={"t"},
                default_limit=0,
            )

        assert mock_gate.call_args.kwargs["default_limit"] == 0

    def test_policy_id_always_consistent(self):
        """PolicyDecision.policy_id is always 'sql.select_gate'."""
        with patch(
            "agent.kernel.policies.validate_and_normalize_sql",
            return_value=GateResult(ok=True, error=None, sql="SELECT 1"),
        ):
            _, decision = apply_sql_select_gate(
                "SELECT 1",
                allowed_tables={"t"},
            )

        assert decision.policy_id == "sql.select_gate"
        assert decision.policy_id == POLICY_SQL_SELECT_GATE

    def test_tool_id_always_sql_execute_select(self):
        """PolicyDecision.tool_id is always 'sql.execute_select'."""
        with patch(
            "agent.kernel.policies.validate_and_normalize_sql",
            return_value=GateResult(ok=False, error="err", sql=None),
        ):
            _, decision = apply_sql_select_gate(
                "BAD SQL",
                allowed_tables={"t"},
            )

        assert decision.tool_id == "sql.execute_select"

    def test_gate_result_preserved(self):
        """GateResult is returned unchanged alongside PolicyDecision."""
        gr = GateResult(ok=True, error=None, sql="SELECT * FROM t")
        with patch(
            "agent.kernel.policies.validate_and_normalize_sql",
            return_value=gr,
        ):
            gate, decision = apply_sql_select_gate(
                "SELECT * FROM t",
                allowed_tables={"t"},
            )

        assert gate is gr
        assert gate.ok is True
        assert gate.sql == "SELECT * FROM t"
        assert decision.ok is True