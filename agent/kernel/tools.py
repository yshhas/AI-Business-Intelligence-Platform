"""Minimal tool helpers — wrap real call paths; record ToolCallRecord."""

from __future__ import annotations

import time
from typing import Any, Callable

from agent.kernel.policies import apply_sql_select_gate
from agent.kernel.types import PolicyDecision, ToolCallRecord


def tool_execute_select(
    sql: str,
    limit: int,
    *,
    allowed_tables: set[str],
    default_limit: int,
    inner_execute: Callable[[str, int], dict[str, Any]],
    tool_calls: list[ToolCallRecord],
    policy_decisions: list[PolicyDecision],
) -> dict[str, Any]:
    """Policy-first SELECT execution (defense-in-depth still in duckdb_service)."""
    t0 = time.perf_counter()
    gate, decision = apply_sql_select_gate(
        sql,
        allowed_tables=allowed_tables,
        default_limit=limit or default_limit,
    )
    policy_decisions.append(decision)
    if not gate.ok or not gate.sql:
        tool_calls.append(
            ToolCallRecord(
                tool_id="sql.execute_select",
                status="error",
                input_summary={"sql_preview": (sql or "")[:200]},
                error_message=gate.error or "SQL policy rejected",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )
        )
        raise RuntimeError(f"SQL Policy rejected query: {gate.error}")

    try:
        # Inner path re-applies Gate inside duckdb_service.run_select
        result = inner_execute(gate.sql, limit or default_limit)
        tool_calls.append(
            ToolCallRecord(
                tool_id="sql.execute_select",
                status="ok",
                input_summary={"sql_preview": gate.sql[:200]},
                output_summary={
                    "row_count": result.get("row_count"),
                    "columns": result.get("columns"),
                },
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )
        )
        return result
    except Exception as exc:  # noqa: BLE001
        tool_calls.append(
            ToolCallRecord(
                tool_id="sql.execute_select",
                status="error",
                input_summary={"sql_preview": gate.sql[:200]},
                error_message=str(exc),
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )
        )
        raise
