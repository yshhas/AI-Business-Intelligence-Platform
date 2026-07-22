"""Smoke M4: to_execution_trace + policy deny materialization + filter columns.

Does not require Redis worker; uses Facade + Gate path when possible.
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from agent.kernel.execution_trace import to_execution_trace  # noqa: E402
from agent.kernel.types import Artifact, PolicyDecision, RunResult, ToolCallRecord  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import AnalysisTask, Dataset, User, Workspace, WorkspaceMember  # noqa: E402
from app.services import run_lifecycle as rl  # noqa: E402
from app.services.task_service import get_execution_trace, list_tasks  # noqa: E402


def main() -> None:
    # Unit: converter
    result = RunResult(
        success=False,
        skill_id="data.bi",
        tool_calls=[
            ToolCallRecord(tool_id="sql.validate_policy", status="ok", latency_ms=1),
            ToolCallRecord(
                tool_id="sql.execute_select",
                status="error",
                error_message="SQL Gate rejected",
            ),
        ],
        policy_decisions=[
            PolicyDecision(
                policy_id="sql.select_gate",
                ok=False,
                reason="Table 'public.secret' is not in allowlist",
                tool_id="sql.execute_select",
            )
        ],
        artifacts=[Artifact(type="sql", payload={"sql": "SELECT 1"}, id="art_sql_1")],
        error_message="SQL Gate rejected",
    )
    execution = to_execution_trace(result, incomplete=True)
    assert execution["summary"]["policy_deny_count"] == 1
    assert execution["policy_decisions"][0]["reason"]
    assert execution["policy_decisions"][0]["call_id"] == "tc_2"
    assert execution["artifacts"][0]["artifact_id"] == "art_sql_1"

    get_settings.cache_clear()
    db = SessionLocal()
    try:
        email = f"m4_{uuid4().hex[:8]}@example.com"
        user = User(
            email=email,
            password_hash=hash_password("password123"),
            display_name="M4",
        )
        db.add(user)
        db.flush()
        ws = Workspace(name="M4 WS", owner_user_id=user.id)
        db.add(ws)
        db.flush()
        db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
        ds = Dataset(
            workspace_id=ws.id,
            name="m4",
            source_type="file",
            original_filename="x.csv",
            storage_path="x",
            duckdb_table=f"ds_{uuid4().hex}",
            schema_json=[{"name": "a", "type": "INTEGER"}],
            row_count=0,
            status="ready",
            created_by=user.id,
            source_config_json={},
        )
        db.add(ds)
        db.flush()
        task = AnalysisTask(
            workspace_id=ws.id,
            dataset_id=ds.id,
            user_id=user.id,
            question="trace me",
            status="failed",
            failure_class=rl.FAILURE_POLICY,
            timeout_seconds=120,
        )
        result_json = {
            "sql": "SELECT 1",
            "platform": {
                "skill_id": "data.bi",
                "data_plane": {"source_type": "file", "primary_table": ds.duckdb_table},
                "execution": execution,
            },
        }
        task.result_json = rl.attach_run_platform(
            result_json,
            status="failed",
            failure_class=rl.FAILURE_POLICY,
            cancel_requested=False,
            timeout_seconds=120,
            task_id=str(task.id) if task.id else str(uuid4()),
        )
        # id assigned on flush
        db.add(task)
        db.flush()
        task.result_json = rl.attach_run_platform(
            result_json,
            status="failed",
            failure_class=rl.FAILURE_POLICY,
            cancel_requested=False,
            timeout_seconds=120,
            task_id=str(task.id),
        )
        rl.apply_trace_columns(task, task.result_json)
        db.commit()
        db.refresh(task)

        assert task.skill_id == "data.bi"
        assert task.source_type == "file"
        assert task.policy_denied is True

        filtered = list_tasks(
            db, workspace_id=ws.id, policy_denied=True, skill_id="data.bi"
        )
        assert any(t.id == task.id for t in filtered)

        trace = get_execution_trace(db, workspace_id=ws.id, task_id=task.id)
        assert trace is not None
        assert trace["execution"]["summary"]["policy_deny_count"] == 1
        assert trace["policy_denied"] is True
        print("M4 smoke OK:", task.id)
    finally:
        db.close()


if __name__ == "__main__":
    main()
