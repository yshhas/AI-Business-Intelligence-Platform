"""Smoke M6: run_artifacts identity + list + content_ref + unavailable stubs.

Does not require Redis worker.
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from agent.kernel.execution_trace import to_execution_trace  # noqa: E402
from agent.kernel.types import Artifact, RunResult  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import AnalysisTask, Dataset, User, Workspace, WorkspaceMember  # noqa: E402
from app.services import artifact_service  # noqa: E402
from app.services import permissions as perm  # noqa: E402
from app.services import run_lifecycle as rl  # noqa: E402


def main() -> None:
    # Stable UUID from Skill → Trace
    art_sql = str(uuid4())
    art_sum = str(uuid4())
    result = RunResult(
        success=True,
        skill_id="data.bi",
        artifacts=[
            Artifact(type="summary", id=art_sum, payload={"text": "ok"}),
            Artifact(type="sql", id=art_sql, payload={"sql": "SELECT 1"}),
            Artifact(
                type="table",
                id=str(uuid4()),
                payload={"columns": ["a"], "rows": [{"a": 1}]},
            ),
        ],
    )
    execution = to_execution_trace(result, incomplete=False)
    assert execution["artifacts"][0]["artifact_id"] == art_sum
    assert execution["artifacts"][1]["artifact_id"] == art_sql

    get_settings.cache_clear()
    db = SessionLocal()
    try:
        email = f"m6_{uuid4().hex[:8]}@example.com"
        user = User(
            email=email,
            password_hash=hash_password("password123"),
            display_name="M6",
        )
        db.add(user)
        db.flush()
        ws = Workspace(name="M6 WS", owner_user_id=user.id)
        db.add(ws)
        db.flush()
        owner = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner")
        db.add(owner)
        viewer_user = User(
            email=f"m6v_{uuid4().hex[:8]}@example.com",
            password_hash=hash_password("password123"),
            display_name="M6V",
        )
        db.add(viewer_user)
        db.flush()
        viewer = WorkspaceMember(
            workspace_id=ws.id, user_id=viewer_user.id, role="viewer"
        )
        db.add(viewer)

        ds = Dataset(
            workspace_id=ws.id,
            name="m6",
            source_type="file",
            original_filename="x.csv",
            storage_path="x",
            duckdb_table=f"ds_{uuid4().hex}",
            schema_json=[{"name": "a", "type": "INTEGER"}],
            row_count=1,
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
            question="artifact me",
            status="succeeded",
            timeout_seconds=120,
        )
        result_json = {
            "summary": "ok",
            "sql": "SELECT 1",
            "table_preview": {"columns": ["a"], "rows": [{"a": 1}]},
            "charts": [],
            "report": None,
            "platform": {
                "skill_id": "data.bi",
                "data_plane": {"source_type": "file", "primary_table": ds.duckdb_table},
                "execution": execution,
            },
        }
        db.add(task)
        db.flush()
        task.result_json = rl.attach_run_platform(
            result_json,
            status="succeeded",
            failure_class=None,
            cancel_requested=False,
            timeout_seconds=120,
            task_id=str(task.id),
        )
        rl.apply_trace_columns(task, task.result_json)
        rows = artifact_service.materialize_for_task(
            db, task, task.result_json, skill_id="data.bi"
        )
        db.commit()
        db.refresh(task)

        by_id = {str(r.id): r for r in rows}
        assert art_sum in by_id
        assert art_sql in by_id
        assert by_id[art_sum].status == "available"
        assert by_id[art_sql].status == "available"

        types = {r.type for r in rows}
        assert "chart" in types and "report" in types
        chart = next(r for r in rows if r.type == "chart")
        report = next(r for r in rows if r.type == "report")
        assert chart.status == "unavailable"
        assert report.status == "unavailable"

        listed = artifact_service.list_for_task(
            db, workspace_id=ws.id, task_id=task.id
        )
        assert len(listed) >= 5

        sql_row = artifact_service.get_for_task(
            db, workspace_id=ws.id, task_id=task.id, artifact_id=by_id[art_sql].id
        )
        assert sql_row is not None
        payload = artifact_service.resolve_payload(task, sql_row)
        assert payload == "SELECT 1"

        lineage = artifact_service.lineage_for(task, sql_row)
        assert lineage["run_id"] == str(task.id)
        assert lineage["skill_id"] == "data.bi"
        assert lineage["dataset_id"] == str(ds.id)
        assert "execution" in lineage["trace"]["path"]

        # Trace ArtifactRefs synced to durable ids + status
        platform = dict(task.result_json.get("platform") or {})
        exec_arts = (platform.get("execution") or {}).get("artifacts") or []
        synced_ids = {a["artifact_id"] for a in exec_arts}
        assert art_sum in synced_ids and art_sql in synced_ids

        # Permissions inherit Run visibility
        db.refresh(viewer)
        assert perm.can(viewer, perm.ARTIFACT_LIST)
        assert perm.can(viewer, perm.ARTIFACT_GET)
        assert not perm.can(viewer, perm.RUN_CREATE, dataset=ds)

        # Partial / failed: unavailable stubs still recorded
        fail = AnalysisTask(
            workspace_id=ws.id,
            dataset_id=ds.id,
            user_id=user.id,
            question="partial",
            status="failed",
            failure_class=rl.FAILURE_SKILL,
            timeout_seconds=120,
        )
        fail.result_json = rl.attach_run_platform(
            {"platform": {"skill_id": "data.bi", "execution": {"artifacts": []}}},
            status="failed",
            failure_class=rl.FAILURE_SKILL,
            cancel_requested=False,
            timeout_seconds=120,
            task_id=str(uuid4()),
        )
        db.add(fail)
        db.flush()
        fail.result_json = rl.attach_run_platform(
            fail.result_json,
            status="failed",
            failure_class=rl.FAILURE_SKILL,
            cancel_requested=False,
            timeout_seconds=120,
            task_id=str(fail.id),
        )
        fail_rows = artifact_service.materialize_for_task(
            db, fail, fail.result_json, skill_id="data.bi"
        )
        db.commit()
        assert len(fail_rows) == 5
        assert all(r.status == "unavailable" for r in fail_rows)

        print("M6 smoke OK:", task.id, "artifacts=", len(listed))
    finally:
        db.close()


if __name__ == "__main__":
    main()
