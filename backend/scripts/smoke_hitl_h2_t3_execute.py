"""HITL H2 T3 smoke: execute-only after approve (success / mismatch / bad SQL).

Does NOT cover FE (H3). Uses mock runtime (no live LLM / DuckDB required).
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
    _resolve_require_sql_approval,
    approve_task,
)
from app.workers.analysis_worker import process_hitl_resume, process_task  # noqa: E402


def _seed(db):
    email = f"hitl_h2_t3_{uuid4().hex[:8]}@example.com"
    user = User(email=email, password_hash=hash_password("password123"), display_name="HITL")
    db.add(user)
    db.flush()
    ws = Workspace(name="HITL H2 T3 WS", owner_user_id=user.id)
    db.add(ws)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
    ds = Dataset(
        workspace_id=ws.id,
        name="hitl_h2_t3",
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


def _set_env() -> None:
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


def _park_approve(db, *, user, ws, ds, question: str) -> AnalysisTask:
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
    assert t is not None and t.hitl_resume_requested is True
    # drain resume wake (process_hitl_resume will still work via flag)
    try:
        task_queue.blocking_dequeue_work(timeout_seconds=1)
    except Exception:  # noqa: BLE001
        pass
    return t


def main() -> None:
    prev_hitl = os.environ.get("HITL_SQL_APPROVAL_ENABLED")
    prev_runtime = os.environ.get("ANALYSIS_RUNTIME")
    db = SessionLocal()
    resume_key = None
    try:
        user, ws, ds = _seed(db)
        _set_env()
        settings = get_settings()
        resume_key = settings.hitl_resume_queue_key
        task_queue.get_redis().delete(resume_key)

        # --- approved → execute → succeeded ---
        t1 = _park_approve(db, user=user, ws=ws, ds=ds, question="execute ok")
        assert process_hitl_resume(t1.id) is True
        db.expire_all()
        t1 = db.get(AnalysisTask, t1.id)
        assert t1 is not None
        assert t1.status == "succeeded", t1.status
        hitl = ((t1.result_json or {}).get("platform") or {}).get("hitl") or {}
        assert hitl.get("executed") is True
        assert (t1.result_json or {}).get("sql")
        assert (t1.result_json or {}).get("charts")
        print("OK: approve → execute-only → succeeded")

        # --- snapshot mismatch → failed (fail-closed) ---
        t2 = _park_approve(db, user=user, ws=ws, ds=ds, question="mismatch")
        # Tamper SQL without updating sha256
        base = dict(t2.result_json or {})
        base["sql"] = 'SELECT 999 AS tampered FROM "evil" LIMIT 10'
        t2.result_json = base
        db.add(t2)
        db.commit()
        assert process_hitl_resume(t2.id) is True  # CAS won
        db.expire_all()
        t2 = db.get(AnalysisTask, t2.id)
        assert t2 is not None
        assert t2.status == "failed", t2.status
        assert t2.failure_class == rl.FAILURE_HITL_SNAPSHOT
        err = (t2.error_message or "").lower()
        assert "mismatch" in err or "diverge" in err, t2.error_message
        hitl2 = ((t2.result_json or {}).get("platform") or {}).get("hitl") or {}
        assert hitl2.get("executed") is False
        check = hitl2.get("snapshot_check") or {}
        assert check.get("ok") is False
        assert check.get("reason_code") in {"mismatch", "sql_snapshot_diverge"}, check
        print("OK: snapshot mismatch → failed")

        # --- execute-phase bad SQL (Gate reject in mock) → failed ---
        t3 = _park_approve(db, user=user, ws=ws, ds=ds, question="bad sql")
        from agent.hitl_snapshot import compute_sql_sha256

        evil = "DROP TABLE users"
        base = dict(t3.result_json or {})
        base["sql"] = evil
        platform = dict(base.get("platform") or {})
        hitl = dict(platform.get("hitl") or {})
        hitl["sql_snapshot"] = evil
        hitl["sql_sha256"] = compute_sql_sha256(evil)
        platform["hitl"] = hitl
        base["platform"] = platform
        t3.result_json = base
        db.add(t3)
        db.commit()
        assert process_hitl_resume(t3.id) is True
        db.expire_all()
        t3 = db.get(AnalysisTask, t3.id)
        assert t3 is not None
        assert t3.status == "failed", t3.status
        assert t3.failure_class in {rl.FAILURE_SKILL, rl.FAILURE_POLICY}
        print("OK: execute-phase Gate reject → failed")

        print("HITL_H2_T3_OK")
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
