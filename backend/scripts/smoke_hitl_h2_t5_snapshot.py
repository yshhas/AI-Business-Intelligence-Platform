"""HITL H2 T5 smoke: SQL snapshot lifecycle + fail-closed edge cases.

Covers:
- park stores sql_snapshot + sql_sha256
- happy approve → execute → succeeded
- sql missing / hash missing / hash invalid / mismatch / sql↔snapshot diverge
- Trace snapshot_check + hitl_snapshot_check step
- double resume after success still no-ops
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import AgentRunStep, AnalysisTask, Dataset, User, Workspace, WorkspaceMember  # noqa: E402
from app.services import queue as task_queue  # noqa: E402
from app.services import run_lifecycle as rl  # noqa: E402
from app.services.task_service import (  # noqa: E402
    _resolve_require_sql_approval,
    approve_task,
)
from app.workers.analysis_worker import process_hitl_resume, process_task  # noqa: E402
from agent.hitl_snapshot import compute_sql_sha256  # noqa: E402


def _seed(db):
    email = f"hitl_h2_t5_{uuid4().hex[:8]}@example.com"
    user = User(email=email, password_hash=hash_password("password123"), display_name="HITL")
    db.add(user)
    db.flush()
    ws = Workspace(name="HITL H2 T5 WS", owner_user_id=user.id)
    db.add(ws)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
    ds = Dataset(
        workspace_id=ws.id,
        name="hitl_h2_t5",
        source_type="file",
        original_filename="x.csv",
        storage_path="x",
        duckdb_table=f"ds_{uuid4().hex}",
        schema_json=[{"name": "a", "type": "INTEGER"}],
        row_count=1,
        status="ready",
        created_by=user.id,
    )
    db.add(ds)
    db.commit()
    db.refresh(user)
    db.refresh(ws)
    db.refresh(ds)
    return user, ws, ds


def _env() -> None:
    os.environ["HITL_SQL_APPROVAL_ENABLED"] = "true"
    os.environ["ANALYSIS_RUNTIME"] = "mock"
    get_settings.cache_clear()


def _pending(db, *, user, ws, ds, question: str) -> AnalysisTask:
    settings = get_settings()
    task = AnalysisTask(
        workspace_id=ws.id,
        dataset_id=ds.id,
        user_id=user.id,
        question=question,
        status="pending",
        skill_id="data.bi",
        skill_version="1.0.0",
        timeout_seconds=120,
        require_sql_approval=_resolve_require_sql_approval(
            settings, skill_id="data.bi", requested=True
        ),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _park(db, *, user, ws, ds, question: str) -> AnalysisTask:
    t = _pending(db, user=user, ws=ws, ds=ds, question=question)
    process_task(t.id)
    db.expire_all()
    t = db.get(AnalysisTask, t.id)
    assert t is not None and t.status == rl.STATUS_AWAITING_APPROVAL
    return t


def _approve(db, *, user, ws, task: AnalysisTask) -> AnalysisTask:
    approve_task(
        db,
        workspace_id=ws.id,
        task_id=task.id,
        user_id=user.id,
        member_role="owner",
    )
    db.expire_all()
    t = db.get(AnalysisTask, task.id)
    assert t is not None and t.hitl_resume_requested is True
    try:
        task_queue.blocking_dequeue_work(timeout_seconds=1)
    except Exception:  # noqa: BLE001
        pass
    return t


def _assert_snapshot_fail(db, task_id, *, reason_code: str) -> AnalysisTask:
    assert process_hitl_resume(task_id) is True
    db.expire_all()
    t = db.get(AnalysisTask, task_id)
    assert t is not None
    assert t.status == "failed", t.status
    assert t.failure_class == rl.FAILURE_HITL_SNAPSHOT, t.failure_class
    hitl = ((t.result_json or {}).get("platform") or {}).get("hitl") or {}
    check = hitl.get("snapshot_check") or {}
    assert check.get("ok") is False
    assert check.get("reason_code") == reason_code, check
    steps = list(
        db.scalars(
            select(AgentRunStep)
            .where(AgentRunStep.task_id == task_id, AgentRunStep.node_name == "hitl_snapshot_check")
        ).all()
    )
    assert len(steps) >= 1
    assert steps[0].status == "error"
    assert (steps[0].output_json or {}).get("reason_code") == reason_code
    return t


def main() -> None:
    prev_hitl = os.environ.get("HITL_SQL_APPROVAL_ENABLED")
    prev_runtime = os.environ.get("ANALYSIS_RUNTIME")
    db = SessionLocal()
    resume_key = None
    try:
        user, ws, ds = _seed(db)
        _env()
        resume_key = get_settings().hitl_resume_queue_key
        task_queue.get_redis().delete(resume_key)

        # --- park persists sql_snapshot + sha ---
        t0 = _park(db, user=user, ws=ws, ds=ds, question="park snapshot")
        hitl0 = ((t0.result_json or {}).get("platform") or {}).get("hitl") or {}
        sql0 = (t0.result_json or {}).get("sql")
        assert isinstance(sql0, str) and sql0.strip()
        assert hitl0.get("sql_snapshot") == sql0.strip()
        assert hitl0.get("sql_sha256") == compute_sql_sha256(sql0)
        assert hitl0.get("snapshot_algo") == "sha256_utf8_strip"
        print("OK: park stores sql_snapshot + sql_sha256")

        # --- happy path ---
        t1 = _approve(db, user=user, ws=ws, task=t0)
        assert process_hitl_resume(t1.id) is True
        db.expire_all()
        t1 = db.get(AnalysisTask, t1.id)
        assert t1 is not None and t1.status == "succeeded"
        print("OK: approve → execute → succeeded")

        # --- double resume after success ---
        task_queue.enqueue_hitl_resume(t1.id)
        assert process_hitl_resume(t1.id) is False
        db.expire_all()
        t1 = db.get(AnalysisTask, t1.id)
        assert t1 is not None and t1.status == "succeeded"
        print("OK: double resume → skip")

        # --- sql missing ---
        t2 = _approve(db, user=user, ws=ws, task=_park(db, user=user, ws=ws, ds=ds, question="no sql"))
        base = dict(t2.result_json or {})
        base["sql"] = ""
        t2.result_json = base
        db.add(t2)
        db.commit()
        _assert_snapshot_fail(db, t2.id, reason_code="sql_missing")
        print("OK: sql missing → failed + Trace")

        # --- hash missing ---
        t3 = _approve(db, user=user, ws=ws, task=_park(db, user=user, ws=ws, ds=ds, question="no hash"))
        base = dict(t3.result_json or {})
        platform = dict(base.get("platform") or {})
        hitl = dict(platform.get("hitl") or {})
        hitl.pop("sql_sha256", None)
        platform["hitl"] = hitl
        base["platform"] = platform
        t3.result_json = base
        db.add(t3)
        db.commit()
        _assert_snapshot_fail(db, t3.id, reason_code="hash_missing")
        print("OK: hash missing → failed + Trace")

        # --- hash invalid ---
        t4 = _approve(db, user=user, ws=ws, task=_park(db, user=user, ws=ws, ds=ds, question="bad hash"))
        base = dict(t4.result_json or {})
        platform = dict(base.get("platform") or {})
        hitl = dict(platform.get("hitl") or {})
        hitl["sql_sha256"] = "not-a-real-hash"
        platform["hitl"] = hitl
        base["platform"] = platform
        t4.result_json = base
        db.add(t4)
        db.commit()
        _assert_snapshot_fail(db, t4.id, reason_code="hash_invalid")
        print("OK: hash invalid → failed + Trace")

        # --- mismatch (tamper sql) ---
        t5 = _approve(db, user=user, ws=ws, task=_park(db, user=user, ws=ws, ds=ds, question="mismatch"))
        base = dict(t5.result_json or {})
        base["sql"] = f'SELECT 9 AS x FROM "{ds.duckdb_table}" LIMIT 1'
        # keep old sql_snapshot + hash → diverge or mismatch
        t5.result_json = base
        db.add(t5)
        db.commit()
        # With sql_snapshot present and different from sql → diverge
        _assert_snapshot_fail(db, t5.id, reason_code="sql_snapshot_diverge")
        print("OK: sql/snapshot diverge -> failed + Trace")

        # --- mismatch when snapshot text removed but hash kept (tamper sql only) ---
        t6 = _approve(db, user=user, ws=ws, task=_park(db, user=user, ws=ws, ds=ds, question="hash mismatch"))
        base = dict(t6.result_json or {})
        platform = dict(base.get("platform") or {})
        hitl = dict(platform.get("hitl") or {})
        hitl.pop("sql_snapshot", None)  # pre-T5 style
        platform["hitl"] = hitl
        base["platform"] = platform
        base["sql"] = f'SELECT 8 AS y FROM "{ds.duckdb_table}" LIMIT 1'
        t6.result_json = base
        db.add(t6)
        db.commit()
        _assert_snapshot_fail(db, t6.id, reason_code="mismatch")
        print("OK: hash mismatch (no sql_snapshot) → failed + Trace")

        print("HITL_H2_T5_OK")
    finally:
        if resume_key:
            try:
                task_queue.get_redis().delete(resume_key)
            except Exception:  # noqa: BLE001
                pass
        if prev_hitl is None:
            os.environ.pop("HITL_SQL_APPROVAL_ENABLED", None)
        else:
            os.environ["HITL_SQL_APPROVAL_ENABLED"] = prev_hitl
        if prev_runtime is None:
            os.environ.pop("ANALYSIS_RUNTIME", None)
        else:
            os.environ["ANALYSIS_RUNTIME"] = prev_runtime
        get_settings.cache_clear()
        db.close()


if __name__ == "__main__":
    main()
