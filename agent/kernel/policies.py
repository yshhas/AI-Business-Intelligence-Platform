"""Policy wrappers — M1 only sql.select_gate over existing SQL Gate."""

from __future__ import annotations

from agent.gates.sql_gate import GateResult, validate_and_normalize_sql
from agent.kernel.types import PolicyDecision


POLICY_SQL_SELECT_GATE = "sql.select_gate"


def apply_sql_select_gate(
    sql: str,
    *,
    allowed_tables: set[str],
    default_limit: int = 200,
) -> tuple[GateResult, PolicyDecision]:
    gate = validate_and_normalize_sql(
        sql,
        allowed_tables=allowed_tables,
        default_limit=default_limit,
    )
    decision = PolicyDecision(
        policy_id=POLICY_SQL_SELECT_GATE,
        ok=gate.ok,
        reason=None if gate.ok else gate.error,
        tool_id="sql.execute_select",
    )
    return gate, decision
