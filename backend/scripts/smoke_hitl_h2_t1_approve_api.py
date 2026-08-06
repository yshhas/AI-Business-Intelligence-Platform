"""HITL H2 T1 smoke: Approve API only (validate + resume enqueue).

Does NOT cover Worker CAS / execute (T2+) or FE (H3).
Seeds via process_task (mock plan) like smoke_hitl_h1.
"""

from __future__ import annotations

import os
import sys
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
from app.services.task_service import (  # noqa: E402
    TaskServiceError,
    _resolve_require_sql_approval,
    approve_task,
    reject_task,
)
from app.workers.analysis_worker import process_task  # noqa: E402


def _seed(db):
    email = f"hitl_h2_t1_{uuid4().hex[:8]}@example.com"
    user = User(email=email, password_hash=hash_password("password123"), display_name="HITL")
    db.add(user)
    db.flush()
    ws = Workspace(name="HITL H2 T1 WS", owner_user_id=user.id)
    db.add(ws)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
    ds = Dataset(
        workspace_id=ws.id,
        name="hitl_h2_t1",
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


def _set_hitl(enabled: bool) -> None:
    os.environ["HITL_SQL_APPROVAL_ENABLED"] = "true" if enabled else "false"
    os.environ["ANALYSIS_RUNTIME"] = "mock"
    get_settings.cache_clear()


def _pending_task(db, *, user, ws, ds, question: str):
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
    t = _pending_task(db, user=user, ws=ws, ds=ds, question=question)
    process_task(t.id)
    db.expire_all()
    t = db.get(AnalysisTask, t.id)
    assert t is not None and t.status == rl.STATUS_AWAITING_APPROVAL, getattr(
        t, "status", None
    )
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

        # --- happy path: approve → still awaiting + flag + resume enqueue ---
        t1 = _park(db, user=user, ws=ws, ds=ds, question="approve me")
        before = task_queue.hitl_resume_queue_length()
        approved = approve_task(
            db,
            workspace_id=ws.id,
            task_id=t1.id,
            user_id=user.id,
            member_role="owner",
        )
        assert approved.status == rl.STATUS_AWAITING_APPROVAL, approved.status
        assert approved.hitl_resume_requested is True
        hitl = ((approved.result_json or {}).get("platform") or {}).get("hitl") or {}
        assert hitl.get("decision") == "approved"
        assert hitl.get("phase") == "awaiting"
        assert hitl.get("resume_requested") is True
        assert task_queue.hitl_resume_queue_length() == before + 1
        # Must NOT flip to running / succeed (T1 boundary)
        assert approved.status != "running"
        assert approved.finished_at is None
        print("OK: approve → awaiting + hitl_resume_requested + resume queue")

        # --- double approve → 409 ---
        try:
            approve_task(
                db,
                workspace_id=ws.id,
                task_id=t1.id,
                user_id=user.id,
                member_role="owner",
            )
            raise AssertionError("expected double-approve 409")
        except TaskServiceError as exc:
            assert exc.status_code == 409, exc.status_code
        print("OK: double approve → 409")

        # --- approve after reject → 409 ---
        t2 = _park(db, user=user, ws=ws, ds=ds, question="reject then approve")
        reject_task(
            db,
            workspace_id=ws.id,
            task_id=t2.id,
            user_id=user.id,
            member_role="owner",
            reason="nope",
        )
        try:
            approve_task(
                db,
                workspace_id=ws.id,
                task_id=t2.id,
                user_id=user.id,
                member_role="owner",
            )
            raise AssertionError("expected approve-after-reject 409")
        except TaskServiceError as exc:
            assert exc.status_code == 409, exc.status_code
        print("OK: approve after reject → 409")

        # --- kill-switch off → 409 (parked row still awaiting) ---
        t3 = _park(db, user=user, ws=ws, ds=ds, question="kill switch")
        _set_hitl(False)
        try:
            approve_task(
                db,
                workspace_id=ws.id,
                task_id=t3.id,
                user_id=user.id,
                member_role="owner",
            )
            raise AssertionError("expected kill-switch 409")
        except TaskServiceError as exc:
            assert exc.status_code == 409, exc.status_code
        db.expire_all()
        t3 = db.get(AnalysisTask, t3.id)
        assert t3 is not None
        assert t3.status == rl.STATUS_AWAITING_APPROVAL
        assert t3.hitl_resume_requested is False
        print("OK: kill-switch off → 409; status unchanged")

        # --- wrong status (pending) → 409 ---
        _set_hitl(True)
        t4 = _pending_task(db, user=user, ws=ws, ds=ds, question="still pending")
        try:
            approve_task(
                db,
                workspace_id=ws.id,
                task_id=t4.id,
                user_id=user.id,
                member_role="owner",
            )
            raise AssertionError("expected pending approve 409")
        except TaskServiceError as exc:
            assert exc.status_code == 409, exc.status_code
        print("OK: approve pending → 409")

        print("HITL_H2_T1_OK")
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
