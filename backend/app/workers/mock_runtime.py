"""Phase 3/5 mock analysis runtime — no LLM, no LangGraph, no SQL generation."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AgentRunStep, AnalysisTask, Dataset
from app.workers.write_fence import write_allowed


def run_mock_analysis(
    db: Session,
    task: AnalysisTask,
    *,
    cancel_check: Callable[[], None] | None = None,
    token: Any | None = None,
) -> dict[str, Any]:
    """Write mock steps and return result_json contract (Phase 5 charts/report placeholders)."""
    from agent.run_control import RunAborted
    from app.core.config import get_settings

    dataset = db.get(Dataset, task.dataset_id)
    dataset_name = dataset.name if dataset else str(task.dataset_id)
    schema_cols = (dataset.schema_json if dataset else []) or []
    task_id: UUID = task.id
    settings = get_settings()
    skill_id = (task.skill_id or "data.bi").strip() or "data.bi"
    prior = task.result_json if isinstance(task.result_json, dict) else {}
    prior_hitl = ((prior.get("platform") or {}).get("hitl") or {})
    hitl_execute = bool(
        prior_hitl.get("phase") == "execute" and prior_hitl.get("decision") == "approved"
    )
    hitl_plan = bool(
        settings.hitl_sql_approval_enabled
        and task.require_sql_approval
        and skill_id == "data.bi"
        and not hitl_execute
    )

    if hitl_execute:
        return _run_mock_hitl_execute(
            db,
            task,
            dataset_name=dataset_name,
            schema_cols=schema_cols,
            prior=prior,
            prior_hitl=prior_hitl,
            cancel_check=cancel_check,
            token=token,
        )

    if hitl_plan:
        # H1: plan-only mock — no charts/report execute fiction; park for approval
        table = (dataset.duckdb_table if dataset else "t") or "t"
        fake_sql = f'SELECT 1 AS hitl_plan FROM "{table}" LIMIT 10'
        for idx, (node_name, inp, out) in enumerate(
            [
                (
                    "load_context",
                    {"dataset_id": str(task.dataset_id), "question": task.question},
                    {"hitl_plan_only": True},
                ),
                (
                    "validate_sql",
                    {"sql_draft": fake_sql},
                    {"sql_final": fake_sql, "policy_id": "sql.select_gate"},
                ),
                (
                    "hitl_plan_done",
                    {"sql_final": fake_sql},
                    {"deferred_execute": True},
                ),
            ],
            start=1,
        ):
            if cancel_check is not None:
                cancel_check()
            if not write_allowed(db, task_id, token):
                raise RunAborted("cancelled")
            t0 = time.perf_counter()
            time.sleep(0.05)
            latency = int((time.perf_counter() - t0) * 1000)
            db.add(
                AgentRunStep(
                    task_id=task.id,
                    step_no=idx,
                    node_name=node_name,
                    status="ok",
                    input_json=inp,
                    output_json=out,
                    latency_ms=latency,
                )
            )
            db.flush()
        if cancel_check is not None:
            cancel_check()
        if not write_allowed(db, task_id, token):
            raise RunAborted("cancelled")
        return {
            "summary": "SQL awaiting human approval (HITL plan phase).",
            "sql": fake_sql,
            "table_preview": {"columns": [], "rows": [], "row_count": 0},
            "charts": [],
            "report": None,
            "limitations": [
                "HITL: plan phase complete — awaiting human approval before execute.",
                "Mock HITL plan — no Data Plane execute.",
            ],
            "mock": True,
            "platform": {
                "skill_id": skill_id,
                "artifact_types": ["sql"],
                "tool_ids": ["sql.validate_policy"],
                "policy_ids": ["sql.select_gate"],
            },
            "task_id": str(task.id),
        }

    steps_spec: list[tuple[str, dict[str, Any], dict[str, Any]]] = [
        (
            "load_context",
            {"dataset_id": str(task.dataset_id), "question": task.question},
            {
                "dataset_name": dataset_name,
                "column_count": len(schema_cols),
                "row_count": dataset.row_count if dataset else 0,
            },
        ),
        (
            "mock_analyze",
            {"runtime": "mock"},
            {
                "note": "Mock runtime — placeholder charts/report for UI contract",
                "echo_question": task.question[:200],
            },
        ),
        (
            "build_charts",
            {"runtime": "mock"},
            {"chart_count": 1, "types": ["bar"]},
        ),
        (
            "write_report",
            {"runtime": "mock"},
            {"title": "分析简报", "has_markdown": True},
        ),
        (
            "finalize",
            {},
            {"status": "succeeded"},
        ),
    ]

    for idx, (node_name, inp, out) in enumerate(steps_spec, start=1):
        if cancel_check is not None:
            cancel_check()
        if not write_allowed(db, task_id, token):
            raise RunAborted("cancelled")
        t0 = time.perf_counter()
        time.sleep(0.15)
        latency = int((time.perf_counter() - t0) * 1000)
        if not write_allowed(db, task_id, token):
            raise RunAborted("cancelled")
        db.add(
            AgentRunStep(
                task_id=task.id,
                step_no=idx,
                node_name=node_name,
                status="ok",
                input_json=inp,
                output_json=out,
                latency_ms=latency,
            )
        )
        db.flush()

    if cancel_check is not None:
        cancel_check()
    if not write_allowed(db, task_id, token):
        raise RunAborted("cancelled")

    preview_cols = [c.get("name", "") for c in schema_cols[:8] if isinstance(c, dict)]
    # Placeholder bar chart so frontend can exercise the same renderer as agent path.
    placeholder_chart = {
        "id": "chart_1",
        "title": "Mock sample (East vs West)",
        "type": "bar",
        "spec": {
            "x": {"field": "region", "type": "nominal"},
            "y": {"field": "total", "type": "quantitative"},
            "data": {
                "columns": ["region", "total"],
                "rows": [
                    {"region": "East", "total": 100},
                    {"region": "West", "total": 250},
                ],
            },
        },
        "rationale": "Mock placeholder chart for Phase 5 UI contract.",
    }
    report = {
        "title": "分析简报",
        "markdown": (
            f"## 结论\n\nMock analysis for dataset **{dataset_name}**.\n\n"
            f"## 关键发现\n\nQuestion: {task.question[:200]}\n\n"
            "## 局限与下一步\n\n- This is ANALYSIS_RUNTIME=mock; switch to agent for real SQL."
        ),
        "sections": [
            {"heading": "结论", "body": f"Mock analysis for dataset '{dataset_name}'."},
            {"heading": "关键发现", "body": task.question[:200]},
            {
                "heading": "局限与下一步",
                "body": "Mock runtime — no real SQL executed.",
            },
        ],
    }
    return {
        "summary": (
            f"Mock analysis complete for dataset '{dataset_name}'. "
            f"Question recorded: {task.question[:120]}"
        ),
        "sql": None,
        "table_preview": {"columns": preview_cols, "rows": []},
        "charts": [placeholder_chart],
        "report": report,
        "limitations": [
            "Mock worker results; no LLM/SQL executed.",
            "Charts/report are placeholders for UI contract compatibility.",
        ],
        "mock": True,
        "platform": {
            "skill_id": "data.bi",
            "artifact_types": ["summary", "chart", "report"],
            "tool_ids": ["chart.build_spec", "report.build"],
            "policy_ids": [],
        },
        "task_id": str(task.id),
    }


def _run_mock_hitl_execute(
    db: Session,
    task: AnalysisTask,
    *,
    dataset_name: str,
    schema_cols: list,
    prior: dict[str, Any],
    prior_hitl: dict[str, Any],
    cancel_check: Callable[[], None] | None,
    token: Any | None,
) -> dict[str, Any]:
    """HITL H2 T4: mock execute-only — same state machine as agent, no Data Plane.

    - Uses approved ``result_json.sql`` snapshot (no LLM / no regenerate)
    - Re-checks sha256 (fail-closed; Worker also checks before invoke)
    - Runs real ``sql.select_gate`` (same Gate as agent); does **not** call DuckDB/RO
    - Emits Trace step names aligned with data.bi graph
    """
    from agent.gates.sql_gate import validate_and_normalize_sql
    from agent.run_control import RunAborted
    from app.core.config import get_settings

    from agent.hitl_snapshot import approved_sql_from_verified, verify_sql_snapshot

    task_id: UUID = task.id
    settings = get_settings()
    dataset = db.get(Dataset, task.dataset_id)
    table = (dataset.duckdb_table if dataset else "") or ""
    allowed: set[str] = {table} if table else set()
    default_limit = int(settings.sql_default_limit or 200)

    # Same fail-closed snapshot contract as Worker / agent_runtime (T5)
    snap = verify_sql_snapshot(prior)
    if not snap.ok:
        raise RuntimeError(snap.message)
    sql_text = approved_sql_from_verified(snap)

    # Same Gate as agent validate_sql — mock does not invent a second policy
    gate = validate_and_normalize_sql(
        sql_text,
        allowed_tables=allowed,
        default_limit=default_limit,
    )
    if not gate.ok or not gate.sql:
        raise RuntimeError(
            f"SQL Gate rejected query: {gate.error or 'policy_denied'}"
        )
    sql_final = gate.sql

    def _step(
        step_no: int,
        node_name: str,
        inp: dict[str, Any],
        out: dict[str, Any],
        *,
        status: str = "ok",
        error_message: str | None = None,
    ) -> None:
        if cancel_check is not None:
            cancel_check()
        if not write_allowed(db, task_id, token):
            raise RunAborted("cancelled")
        t0 = time.perf_counter()
        time.sleep(0.05)
        latency = int((time.perf_counter() - t0) * 1000)
        db.add(
            AgentRunStep(
                task_id=task.id,
                step_no=step_no,
                node_name=node_name,
                status=status,
                input_json=inp,
                output_json=out,
                error_message=error_message,
                latency_ms=latency,
            )
        )
        db.flush()

    # Step names match agent graph (load → validate → execute → summarize → charts → report)
    _step(
        1,
        "load_context",
        {"hitl_execute_only": True, "dataset_id": str(task.dataset_id)},
        {
            "hitl_execute_only": True,
            "approved_sql": True,
            "duckdb_table": table,
            "column_count": len(schema_cols),
        },
    )
    _step(
        2,
        "validate_sql",
        {"sql_draft": sql_text[:500]},
        {"sql_final": sql_final[:500], "policy_id": "sql.select_gate", "tool_id": "sql.validate_policy"},
    )
    _step(
        3,
        "execute_sql",
        {"sql": sql_final[:500]},
        {
            "row_count": 1,
            "mock_execute": True,
            "tool_id": "sql.execute_select",
            "note": "Mock fiction — Data Plane not invoked",
        },
    )
    _step(
        4,
        "summarize",
        {"runtime": "mock"},
        {"hitl_execute_only": True},
    )
    _step(
        5,
        "build_charts",
        {"runtime": "mock"},
        {"chart_count": 1, "types": ["bar"], "tool_id": "chart.build_spec"},
    )
    _step(
        6,
        "write_report",
        {"runtime": "mock"},
        {"title": "分析简报", "has_markdown": True, "tool_id": "report.build"},
    )

    if cancel_check is not None:
        cancel_check()
    if not write_allowed(db, task_id, token):
        raise RunAborted("cancelled")

    preview_cols = [c.get("name", "") for c in schema_cols[:8] if isinstance(c, dict)]
    placeholder_chart = {
        "id": "chart_1",
        "title": "HITL execute (mock)",
        "type": "bar",
        "spec": {
            "x": {"field": "region", "type": "nominal"},
            "y": {"field": "total", "type": "quantitative"},
            "data": {
                "columns": ["region", "total"],
                "rows": [
                    {"region": "East", "total": 100},
                    {"region": "West", "total": 250},
                ],
            },
        },
        "rationale": "Mock HITL execute placeholder — not from Data Plane rows.",
    }
    report = {
        "title": "分析简报",
        "markdown": (
            f"## 结论\n\nHITL-approved mock execute for **{dataset_name}**.\n\n"
            f"## SQL\n\n```sql\n{sql_final[:500]}\n```\n"
        ),
        "sections": [
            {"heading": "结论", "body": f"HITL execute (mock) for '{dataset_name}'."},
            {"heading": "SQL", "body": sql_final[:500]},
        ],
    }
    hitl_out = dict(prior_hitl)
    hitl_out.update(
        {
            "required": True,
            "phase": "execute",
            "decision": "approved",
            "executed": True,
            "resume_requested": False,
            "runtime": "mock",
        }
    )
    return {
        "summary": (
            f"HITL execute complete (mock) for dataset '{dataset_name}'. "
            f"Approved SQL validated by Gate; Data Plane not invoked."
        ),
        "sql": sql_final,
        "table_preview": {
            "columns": preview_cols or ["hitl_plan"],
            "rows": [{(preview_cols[0] if preview_cols else "hitl_plan"): 1}],
            "row_count": 1,
        },
        "charts": [placeholder_chart],
        "report": report,
        "limitations": [
            "HITL: execute-only — approved SQL snapshot (no regenerate).",
            "Mock HITL execute — sql.select_gate applied; Data Plane not invoked.",
            "Charts/report are placeholders for UI contract compatibility.",
        ],
        "mock": True,
        "platform": {
            "skill_id": "data.bi",
            "artifact_types": ["summary", "sql", "table", "chart", "report"],
            "tool_ids": [
                "sql.validate_policy",
                "sql.execute_select",
                "chart.build_spec",
                "report.build",
            ],
            "policy_ids": ["sql.select_gate"],
            "hitl": hitl_out,
        },
        "task_id": str(task.id),
    }


def assert_mock_only(runtime: str) -> None:
    """Kept for Phase 3 docs/tests; Phase 4+ worker accepts mock|agent."""
    if runtime != "mock":
        raise RuntimeError(f"assert_mock_only: expected 'mock', got {runtime!r}")
