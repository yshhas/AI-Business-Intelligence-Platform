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

    dataset = db.get(Dataset, task.dataset_id)
    dataset_name = dataset.name if dataset else str(task.dataset_id)
    schema_cols = (dataset.schema_json if dataset else []) or []
    task_id: UUID = task.id

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


def assert_mock_only(runtime: str) -> None:
    """Kept for Phase 3 docs/tests; Phase 4+ worker accepts mock|agent."""
    if runtime != "mock":
        raise RuntimeError(f"assert_mock_only: expected 'mock', got {runtime!r}")
