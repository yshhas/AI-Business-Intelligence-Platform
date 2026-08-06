"""HITL H2 T2 smoke: Worker CAS resume awaiting→running (+ T3 execute-only).

CAS + execute closed loop: happy path ends succeeded. FE (H3) not covered.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import AnalysisTask, Dataset, User, Workspace, WorkspaceMember  # noqa: E402
from app.services import queue as task_queue  # noqa: E402
from app.services import run_lifecycle as rl  # noqa: E402
from app.services import runtime_essentials as rt  # noqa: E402
from app.services.task_service import (  # noqa: E402
    _resolve_require_sql_approval,
    approve_task,
    cancel_task,
    reject_task,
)
from app.workers.analysis_worker import (  # noqa: E402
    process_hitl_resume,
    process_task,
    recover_pending_hitl_resumes,
)


def _seed(db):
    email = f"hitl_h2_t2_{uuid4().hex[:8]}@example.com"
    user = User(email=email, password_hash=hash_password("password123"), display_name="HITL")
    db.add(user)
    db.flush()
    ws = Workspace(name="HITL H2 T2 WS", owner_user_id=user.id)
    db.add(ws)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
    ds = Dataset(
        workspace_id=ws.id,
        name="hitl_h2_t2",
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


def _set_hitl(enabled: bool = True) -> None:
    os.environ["HITL_SQL_APPROVAL_ENABLED"] = "true" if enabled else "false"
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


def _park_and_approve(db, *, user, ws, ds, question: str) -> AnalysisTask:
    t = _pending(db, user=user, ws=ws, ds=ds, question=question)
    process_task(t.id)
    db.expire_all()
    t = db.get(AnalysisTask, t.id)
    assert t is not None and t.status == rl.STATUS_AWAITING_APPROVAL
    approve_task(
        db,
        workspace_id=ws.id,
        task_id=t.id,
        user_id=user.id,
        member_role="owner",
    )
    db.expire_all()
    t = db.get(AnalysisTask, t.id)
    assert t is not None
    assert t.status == rl.STATUS_AWAITING_APPROVAL
    assert t.hitl_resume_requested is True
    return t


def main() -> None:
    prev_hitl = os.environ.get("HITL_SQL_APPROVAL_ENABLED")
    prev_runtime = os.environ.get("ANALYSIS_RUNTIME")
    db = SessionLocal()
    resume_key = None
    try:
        user, ws, ds = _seed(db)
        _set_hitl(True)
        settings = get_settings()
        resume_key = settings.hitl_resume_queue_key
        r = task_queue.get_redis()
        r.delete(resume_key)

        # --- happy path: approve → resume CAS → running / phase=execute ---
        t1 = _park_and_approve(db, user=user, ws=ws, ds=ds, question="resume me")
        assert task_queue.hitl_resume_queue_length() >= 1
        work = task_queue.blocking_dequeue_work(timeout_seconds=2)
        assert work is not None and work[0] == "hitl_resume" and work[1] == t1.id
        won = process_hitl_resume(t1.id)
        assert won is True
        db.expire_all()
        t1 = db.get(AnalysisTask, t1.id)
        assert t1 is not None
        assert t1.status == "succeeded", t1.status
        assert t1.hitl_resume_requested is False
        hitl = ((t1.result_json or {}).get("platform") or {}).get("hitl") or {}
        assert hitl.get("phase") == "execute", hitl
        assert hitl.get("decision") == "approved"
        assert hitl.get("executed") is True
        assert t1.finished_at is not None
        print("OK: resume CAS → execute-only → succeeded")

        # --- double resume → CAS lose / skip ---
        task_queue.enqueue_hitl_resume(t1.id)
        work2 = task_queue.blocking_dequeue_work(timeout_seconds=2)
        assert work2 is not None and work2[0] == "hitl_resume"
        won2 = process_hitl_resume(t1.id)
        assert won2 is False
        db.expire_all()
        t1 = db.get(AnalysisTask, t1.id)
        assert t1 is not None and t1.status == "succeeded"
        print("OK: double resume → skip")

        # --- reject then resume arrives → skip ---
        t2 = _park_and_approve(db, user=user, ws=ws, ds=ds, question="reject race")
        # drain wake from approve
        _ = task_queue.blocking_dequeue_work(timeout_seconds=2)
        reject_task(
            db,
            workspace_id=ws.id,
            task_id=t2.id,
            user_id=user.id,
            member_role="owner",
            reason="nope",
        )
        task_queue.enqueue_hitl_resume(t2.id)
        assert process_hitl_resume(t2.id) is False
        db.expire_all()
        t2 = db.get(AnalysisTask, t2.id)
        assert t2 is not None and t2.status == "failed"
        assert t2.failure_class == rl.FAILURE_HITL_REJECTED
        print("OK: resume after reject → skip")

        # --- cancel then resume → skip ---
        t3 = _park_and_approve(db, user=user, ws=ws, ds=ds, question="cancel race")
        _ = task_queue.blocking_dequeue_work(timeout_seconds=2)
        cancel_task(
            db,
            workspace_id=ws.id,
            task_id=t3.id,
            user_id=user.id,
            member_role="owner",
        )
        assert process_hitl_resume(t3.id) is False
        db.expire_all()
        t3 = db.get(AnalysisTask, t3.id)
        assert t3 is not None and t3.status == "cancelled"
        print("OK: resume after cancel → skip")

        # --- timeout then resume → skip ---
        t4 = _park_and_approve(db, user=user, ws=ws, ds=ds, question="timeout race")
        _ = task_queue.blocking_dequeue_work(timeout_seconds=2)
        t4.timeout_seconds = 1
        t4.started_at = datetime.now(UTC) - timedelta(seconds=30)
        db.add(t4)
        db.commit()
        n = rt.expire_awaiting_approval(db, get_settings())
        assert n >= 1
        assert process_hitl_resume(t4.id) is False
        db.expire_all()
        t4 = db.get(AnalysisTask, t4.id)
        assert t4 is not None and t4.status == "timed_out"
        print("OK: resume after timeout → skip")

        # --- Worker restart recovery (flag set, no Redis) ---
        t5 = _pending(db, user=user, ws=ws, ds=ds, question="recover me")
        process_task(t5.id)
        db.expire_all()
        t5 = db.get(AnalysisTask, t5.id)
        assert t5 is not None and t5.status == rl.STATUS_AWAITING_APPROVAL
        # Set resume flag without enqueue (simulate lost Redis wake)
        t5.hitl_resume_requested = True
        base = dict(t5.result_json or {})
        platform = dict(base.get("platform") or {})
        hitl = dict(platform.get("hitl") or {})
        hitl.update({"decision": "approved", "resume_requested": True, "phase": "awaiting"})
        platform["hitl"] = hitl
        t5.result_json = {**base, "platform": platform}
        db.add(t5)
        db.commit()
        r.delete(resume_key)
        won_r = recover_pending_hitl_resumes()
        assert won_r >= 1
        db.expire_all()
        t5 = db.get(AnalysisTask, t5.id)
        assert t5 is not None
        assert t5.status == "succeeded", t5.status
        assert t5.hitl_resume_requested is False
        hitl5 = ((t5.result_json or {}).get("platform") or {}).get("hitl") or {}
        assert hitl5.get("phase") == "execute"
        assert hitl5.get("executed") is True
        print("OK: recover_pending_hitl_resumes → succeeded")

        print("HITL_H2_T2_OK")
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
