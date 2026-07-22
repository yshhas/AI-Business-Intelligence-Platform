"""T-10 smoke: SSE task progress events (DB poll; not LLM token stream)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import AgentRunStep, AnalysisTask, Dataset, User, Workspace, WorkspaceMember  # noqa: E402
from app.services import task_events  # noqa: E402


def _parse_sse(chunk: str) -> tuple[str, dict]:
    event = "message"
    data_lines: list[str] = []
    for line in chunk.strip().splitlines():
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    return event, json.loads("\n".join(data_lines))


def main() -> None:
    get_settings.cache_clear()
    db = SessionLocal()
    try:
        email = f"sse_{uuid4().hex[:8]}@example.com"
        user = User(
            email=email,
            password_hash=hash_password("password123"),
            display_name="SSE",
        )
        db.add(user)
        db.flush()
        ws = Workspace(name="SSE WS", owner_user_id=user.id)
        db.add(ws)
        db.flush()
        db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
        ds = Dataset(
            workspace_id=ws.id,
            name="sse",
            source_type="file",
            original_filename="x.csv",
            storage_path="x",
            duckdb_table=f"ds_{uuid4().hex}",
            schema_json=[{"name": "a", "type": "INTEGER"}],
            row_count=0,
            status="ready",
            created_by=user.id,
        )
        db.add(ds)
        db.flush()

        task = AnalysisTask(
            workspace_id=ws.id,
            dataset_id=ds.id,
            user_id=user.id,
            question="sse smoke",
            status="succeeded",
            skill_id="data.bi",
            skill_version="1.0.0",
        )
        db.add(task)
        db.flush()
        db.add(
            AgentRunStep(
                task_id=task.id,
                step_no=1,
                node_name="generate_sql",
                status="succeeded",
                output_json={
                    "sql_draft": "SELECT 1",
                    "secret_reason": "must_not_leak",
                    "llm": {"latency_ms": 12, "attempts": 1},
                },
            )
        )
        db.commit()
        workspace_id = ws.id
        task_id = task.id
    finally:
        db.close()

    events: list[tuple[str, dict]] = []
    for chunk in task_events.iter_task_progress_events(
        workspace_id=workspace_id,
        task_id=task_id,
        poll_seconds=0.1,
        heartbeat_seconds=60,
        max_seconds=5,
    ):
        events.append(_parse_sse(chunk))

    names = [e[0] for e in events]
    assert names[0] == "snapshot", names
    assert names[-1] == "terminal", names
    assert "heartbeat" not in names

    snap = events[0][1]
    assert snap["task"]["status"] == "succeeded"
    assert snap["task"]["skill_version"] == "1.0.0"
    assert len(snap["steps"]) == 1
    step_out = snap["steps"][0]["output_json"] or {}
    assert "sql_draft" in step_out
    assert "llm" in step_out
    assert "secret_reason" not in step_out, "progress brief must not dump full output_json"
    assert events[-1][1]["status"] == "succeeded"
    print("SSE_TERMINAL_SNAPSHOT_OK")

    # Missing task
    missing = list(
        task_events.iter_task_progress_events(
            workspace_id=workspace_id,
            task_id=uuid4(),
            poll_seconds=0.1,
            max_seconds=2,
        )
    )
    err_event, err_data = _parse_sse(missing[0])
    assert err_event == "error"
    assert "not found" in err_data["message"].lower()
    print("SSE_MISSING_TASK_OK")

    # Brief truncates long sql_draft + strips unknown keys
    db = SessionLocal()
    try:
        db.add(
            AgentRunStep(
                task_id=task_id,
                step_no=2,
                node_name="summarize",
                status="succeeded",
                output_json={"sql_draft": "B" * 400, "noise": "x"},
            )
        )
        db.commit()
        from app.services import task_service

        steps = task_service.list_steps(db, task_id=task_id)
        long_step = next(s for s in steps if s.step_no == 2)
        briefed = task_events._step_brief(long_step)
        draft = (briefed.get("output_json") or {}).get("sql_draft", "")
        assert len(draft) < 400
        assert draft.endswith("…")
        assert "noise" not in (briefed.get("output_json") or {})
    finally:
        db.close()
    print("SSE_BRIEF_TRUNCATE_OK")
    print("OK: smoke_task_events")


if __name__ == "__main__":
    main()
