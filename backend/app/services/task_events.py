"""T-10: Task progress SSE — polls existing Task/Steps tables (no new broker).

Events describe Run progress only (status / step completion). Not LLM token streams.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from datetime import datetime
from typing import Any
from uuid import UUID

from app.core.db import SessionLocal
from app.schemas.task import StepOut, TaskOut
from app.services import run_lifecycle as rl
from app.services import task_service


def _sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, default=_json_default, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)!r} is not JSON serializable")


def _step_brief(step: Any) -> dict[str, Any]:
    """Progress-safe step view — no hidden LLM reasoning / full payloads."""
    out = StepOut.model_validate(step)
    brief_output: dict[str, Any] | None = None
    if out.output_json:
        brief_output = {}
        for key in ("sql_draft", "sql_final", "chart_count", "title", "llm"):
            if key in out.output_json:
                val = out.output_json[key]
                if key == "sql_draft" and isinstance(val, str) and len(val) > 240:
                    val = val[:240] + "…"
                brief_output[key] = val
        if not brief_output:
            brief_output = None
    return {
        "id": str(out.id),
        "task_id": str(out.task_id),
        "step_no": out.step_no,
        "node_name": out.node_name,
        "status": out.status,
        "latency_ms": out.latency_ms,
        "error_message": out.error_message,
        "output_json": brief_output,
        "created_at": out.created_at.isoformat() if out.created_at else None,
    }


def _task_brief(task: Any) -> dict[str, Any]:
    t = TaskOut.model_validate(task)
    return {
        "id": str(t.id),
        "status": t.status,
        "failure_class": t.failure_class,
        "skill_id": t.skill_id,
        "skill_version": t.skill_version,
        "error_message": t.error_message,
        "cancel_requested": t.cancel_requested,
        "started_at": t.started_at.isoformat() if t.started_at else None,
        "finished_at": t.finished_at.isoformat() if t.finished_at else None,
    }


def iter_task_progress_events(
    *,
    workspace_id: UUID,
    task_id: UUID,
    poll_seconds: float = 0.5,
    heartbeat_seconds: float = 5.0,
    max_seconds: float = 600.0,
) -> Iterator[str]:
    """Yield SSE chunks until Run reaches a terminal status or timeout."""
    started = time.monotonic()
    last_step_no = 0
    last_status: str | None = None
    sent_snapshot = False
    last_heartbeat = started

    while True:
        now = time.monotonic()
        if now - started > max_seconds:
            yield _sse(
                "error",
                {"message": "SSE watch timed out; client may fall back to polling"},
            )
            return

        db = SessionLocal()
        try:
            task = task_service.get_task(
                db, workspace_id=workspace_id, task_id=task_id
            )
            if task is None:
                yield _sse("error", {"message": "Task not found"})
                return

            steps = task_service.list_steps(db, task_id=task_id)

            if not sent_snapshot:
                yield _sse(
                    "snapshot",
                    {
                        "task": _task_brief(task),
                        "steps": [_step_brief(s) for s in steps],
                    },
                )
                last_step_no = max((s.step_no for s in steps), default=0)
                last_status = task.status
                sent_snapshot = True
            else:
                for step in steps:
                    if step.step_no > last_step_no:
                        yield _sse("step", {"step": _step_brief(step)})
                        last_step_no = step.step_no
                if task.status != last_status:
                    yield _sse(
                        "status",
                        {"status": task.status, "task": _task_brief(task)},
                    )
                    last_status = task.status

            if task.status in rl.TERMINAL_STATUSES:
                yield _sse(
                    "terminal",
                    {"status": task.status, "task": _task_brief(task)},
                )
                return
        finally:
            db.close()

        if now - last_heartbeat >= heartbeat_seconds:
            yield _sse("heartbeat", {"ts": time.time()})
            last_heartbeat = time.monotonic()

        time.sleep(max(0.1, float(poll_seconds)))
