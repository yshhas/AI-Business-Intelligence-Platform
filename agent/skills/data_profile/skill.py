"""Skill data.profile — deterministic dataset profiling (Wave 3).

Same Kernel contracts as data.bi: RunRequest → Policy-gated SELECT → Trace/Artifacts.
No LangGraph required; fixed procedural pipeline (not ReAct).
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from agent.kernel.tools import tool_execute_select
from agent.kernel.types import (
    Artifact,
    PolicyDecision,
    RunRequest,
    RunResult,
    ToolCallRecord,
)
from agent.state import StepRecord

SKILL_ID = "data.profile"
_MAX_PROFILE_COLUMNS = 8


def _quote_ident(name: str) -> str:
    if "." in name:
        parts = name.split(".", 1)
        return f'"{parts[0]}"."{parts[1]}"'
    return f'"{name}"'


def _quote_col(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def run_data_profile_skill(request: RunRequest) -> RunResult:
    if request.execute_select is None:
        return RunResult(
            success=False,
            skill_id=SKILL_ID,
            error_message="execute_select callback required for data.profile",
        )

    tool_calls: list[ToolCallRecord] = []
    policy_decisions: list[PolicyDecision] = []
    steps: list[StepRecord] = []

    allowed = set(request.policy_context.get("allowed_tables") or [])
    if request.duckdb_table:
        allowed.add(request.duckdb_table)
    default_limit = int(request.policy_context.get("default_limit") or 200)
    table = request.duckdb_table
    schema = list(request.schema or [])
    inp = request.input or {}
    question = str(inp.get("question") or "profile dataset")

    inner = request.execute_select

    def execute_select(sql: str, limit: int) -> dict[str, Any]:
        if request.cancel_check is not None:
            request.cancel_check()
        return tool_execute_select(
            sql,
            limit,
            allowed_tables=allowed,
            default_limit=default_limit,
            inner_execute=inner,
            tool_calls=tool_calls,
            policy_decisions=policy_decisions,
        )

    if request.cancel_check is not None:
        request.cancel_check()

    # --- load_context ---
    steps.append(
        StepRecord(
            node_name="load_context",
            status="ok",
            input_json={"question": question, "table": table},
            output_json={
                "skill_id": SKILL_ID,
                "column_count": len(schema),
                "source_type": inp.get("source_type") or request.runtime_hints.get("source_type"),
            },
        )
    )

    if not table:
        return RunResult(
            success=False,
            skill_id=SKILL_ID,
            steps=steps,
            tool_calls=tool_calls,
            policy_decisions=policy_decisions,
            error_message="duckdb_table / primary relation required",
        )

    rel = _quote_ident(table)
    cols = [
        str(c.get("name"))
        for c in schema
        if isinstance(c, dict) and c.get("name")
    ][:_MAX_PROFILE_COLUMNS]

    # --- profile_schema (Policy-gated SELECTs) ---
    profiles: list[dict[str, Any]] = []
    errors: list[str] = []
    for col in cols:
        if request.cancel_check is not None:
            request.cancel_check()
        sql = (
            f"SELECT COUNT(*) AS row_n, COUNT(DISTINCT {_quote_col(col)}) AS distinct_n "
            f"FROM {rel}"
        )
        try:
            preview = execute_select(sql, default_limit)
            row = (preview.get("rows") or [None])[0]
            row_n = distinct_n = None
            if isinstance(row, dict):
                row_n = row.get("row_n")
                distinct_n = row.get("distinct_n")
            elif isinstance(row, (list, tuple)):
                row_n = row[0] if len(row) > 0 else None
                distinct_n = row[1] if len(row) > 1 else None
            profiles.append(
                {
                    "column": col,
                    "row_count": row_n,
                    "distinct_count": distinct_n,
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{col}: {exc}")

    steps.append(
        StepRecord(
            node_name="profile_schema",
            status="ok" if profiles else "error",
            input_json={"columns": cols, "table": table},
            output_json={"profiles": profiles, "errors": errors or None},
            error_message="; ".join(errors) if profiles == [] and errors else None,
        )
    )

    if not profiles:
        return RunResult(
            success=False,
            skill_id=SKILL_ID,
            steps=steps,
            tool_calls=tool_calls,
            policy_decisions=policy_decisions,
            error_message=errors[0] if errors else "profile failed",
            limitations=["No column profiles could be collected under Policy Gate."],
        )

    # --- summarize / report (heuristic; no LLM required) ---
    row_n = profiles[0].get("row_count")
    summary = (
        f"Profiled table {table}: {len(profiles)} columns"
        + (f", ~{row_n} rows." if row_n is not None else ".")
    )
    lines = [
        f"# Dataset profile — {table}",
        "",
        f"Question: {question}",
        "",
        "| column | rows | distinct |",
        "|---|---:|---:|",
    ]
    for p in profiles:
        lines.append(
            f"| {p['column']} | {p.get('row_count')} | {p.get('distinct_count')} |"
        )
    if errors:
        lines.extend(["", "## Notes", *[f"- {e}" for e in errors]])
    report_md = "\n".join(lines)

    steps.append(
        StepRecord(
            node_name="summarize",
            status="ok",
            output_json={"summary": summary},
        )
    )
    steps.append(
        StepRecord(
            node_name="write_report",
            status="ok",
            output_json={"title": f"Profile {table}", "markdown": report_md},
        )
    )

    preview = {
        "columns": ["column", "row_count", "distinct_count"],
        "rows": [
            [p["column"], p.get("row_count"), p.get("distinct_count")] for p in profiles
        ],
        "row_count": len(profiles),
    }

    artifacts = [
        Artifact(
            type="summary",
            id=str(uuid4()),
            payload={"text": summary},
        ),
        Artifact(
            type="table",
            id=str(uuid4()),
            payload={
                "columns": preview["columns"],
                "rows": preview["rows"],
            },
        ),
        Artifact(
            type="report",
            id=str(uuid4()),
            payload={"title": f"Profile {table}", "markdown": report_md},
        ),
    ]

    return RunResult(
        success=True,
        skill_id=SKILL_ID,
        artifacts=artifacts,
        tool_calls=tool_calls,
        policy_decisions=policy_decisions,
        steps=steps,
        limitations=(
            ["Some columns failed profiling under Gate/engine constraints."]
            if errors
            else []
        ),
    )
