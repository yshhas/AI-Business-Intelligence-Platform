"""HITL H1 smoke: plan→awaiting, reject, cancel-wait, timeout sweeper, kill-switch.

Does NOT cover Approve→Execute (H2).
Seeds tasks directly (no Redis enqueue) to avoid racing a live Worker.
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
from app.services import run_lifecycle as rl  # noqa: E402
from app.services import runtime_essentials as rt  # noqa: E402
from app.services.task_service import (  # noqa: E402
    _resolve_require_sql_approval,
    cancel_task,
    reject_task,
)
from app.workers.analysis_worker import process_task  # noqa: E402


def _seed(db):
    email = f"hitl_h1_{uuid4().hex[:8]}@example.com"
    user = User(email=email, password_hash=hash_password("password123"), display_name="HITL")
    db.add(user)
    db.flush()
    ws = Workspace(name="HITL H1 WS", owner_user_id=user.id)
    db.add(ws)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
    ds = Dataset(
        workspace_id=ws.id,
        name="hitl_h1",
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


def _pending_task(db, *, user, ws, ds, question: str, require: bool, skill_id: str = "data.bi"):
    settings = get_settings()
    task = AnalysisTask(
        workspace_id=ws.id,
        dataset_id=ds.id,
        user_id=user.id,
        question=question,
        status="pending",
        skill_id=skill_id,
        skill_version="1.0.0",
        timeout_seconds=120,
        require_sql_approval=_resolve_require_sql_approval(
            settings, skill_id=skill_id, requested=require
        ),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def main() -> None:
    prev_hitl = os.environ.get("HITL_SQL_APPROVAL_ENABLED")
    prev_runtime = os.environ.get("ANALYSIS_RUNTIME")
    db = SessionLocal()
    try:
        user, ws, ds = _seed(db)
        _set_hitl(True)
        assert get_settings().hitl_sql_approval_enabled is True
        assert get_settings().analysis_runtime == "mock"

        # --- enter awaiting_approval (mock plan) ---
        t1 = _pending_task(db, user=user, ws=ws, ds=ds, question="hitl plan", require=True)
        assert t1.require_sql_approval is True, t1.require_sql_approval
        process_task(t1.id)
        db.expire_all()
        t1 = db.get(AnalysisTask, t1.id)
        assert t1 is not None
        assert t1.status == rl.STATUS_AWAITING_APPROVAL, t1.status
        assert t1.approval_requested_at is not None
        assert (t1.result_json or {}).get("sql"), t1.result_json
        platform = (t1.result_json or {}).get("platform") or {}
        assert (platform.get("hitl") or {}).get("phase") == "awaiting"
        print("OK: plan → awaiting_approval")

        # --- reject ---
        rejected = reject_task(
            db,
            workspace_id=ws.id,
            task_id=t1.id,
            user_id=user.id,
            member_role="owner",
            reason="nope",
        )
        assert rejected.status == "failed"
        assert rejected.failure_class == rl.FAILURE_HITL_REJECTED
        print("OK: reject → hitl_rejected")

        # --- cancel while waiting ---
        t2 = _pending_task(db, user=user, ws=ws, ds=ds, question="cancel me", require=True)
        process_task(t2.id)
        db.expire_all()
        t2 = db.get(AnalysisTask, t2.id)
        assert t2 is not None and t2.status == rl.STATUS_AWAITING_APPROVAL, getattr(
            t2, "status", None
        )
        cancelled = cancel_task(
            db,
            workspace_id=ws.id,
            task_id=t2.id,
            user_id=user.id,
            member_role="owner",
        )
        assert cancelled.status == "cancelled", cancelled.status
        assert cancelled.failure_class == rl.FAILURE_CANCELLED
        print("OK: cancel while awaiting_approval")

        # --- timeout sweeper ---
        t3 = _pending_task(db, user=user, ws=ws, ds=ds, question="timeout me", require=True)
        process_task(t3.id)
        db.expire_all()
        t3 = db.get(AnalysisTask, t3.id)
        assert t3 is not None and t3.status == rl.STATUS_AWAITING_APPROVAL
        t3.timeout_seconds = 1
        t3.started_at = datetime.now(UTC) - timedelta(seconds=30)
        db.add(t3)
        db.commit()
        n = rt.expire_awaiting_approval(db, get_settings())
        assert n >= 1, n
        db.expire_all()
        t3 = db.get(AnalysisTask, t3.id)
        assert t3 is not None
        assert t3.status == "timed_out", t3.status
        assert t3.failure_class == rl.FAILURE_TIMEOUT
        print("OK: expire_awaiting_approval → timed_out")

        # --- kill-switch off ---
        _set_hitl(False)
        assert get_settings().hitl_sql_approval_enabled is False
        t4 = _pending_task(db, user=user, ws=ws, ds=ds, question="no hitl", require=True)
        assert t4.require_sql_approval is False
        process_task(t4.id)
        db.expire_all()
        t4 = db.get(AnalysisTask, t4.id)
        assert t4 is not None
        assert t4.status == "succeeded", t4.status
        print("OK: kill-switch off → no awaiting_approval")

        # --- in-flight includes awaiting (R5) ---
        _set_hitl(True)
        parked = AnalysisTask(
            workspace_id=ws.id,
            dataset_id=ds.id,
            user_id=user.id,
            question="parked capacity",
            status=rl.STATUS_AWAITING_APPROVAL,
            require_sql_approval=True,
            skill_id="data.bi",
            timeout_seconds=120,
            started_at=datetime.now(UTC),
        )
        db.add(parked)
        db.commit()
        assert rt.count_running(db) >= 1
        print("OK: in-flight counts awaiting_approval")

        # --- profile ignores flag ---
        t5 = _pending_task(
            db, user=user, ws=ws, ds=ds, question="profile", require=True, skill_id="data.profile"
        )
        assert t5.require_sql_approval is False
        print("OK: data.profile ignores require_sql_approval")

        # --- resolve helper mirrors create_task kill-switch ---
        assert (
            _resolve_require_sql_approval(get_settings(), skill_id="data.bi", requested=True)
            is True
        )
        _set_hitl(False)
        assert (
            _resolve_require_sql_approval(get_settings(), skill_id="data.bi", requested=True)
            is False
        )
        print("OK: create-flag resolution helpers")

        print("HITL_H1_OK")
    finally:
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
