"""HITL H2 T4 smoke: mock runtime HITL resume → execute-only contract.

Covers:
- mock approved → succeeded (mock:true, Gate+snapshot, no regen)
- mock snapshot mismatch → failed
- mock Gate reject → failed

Does NOT cover agent Plane, FE (H3), or release-gate wiring.
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
from app.models import AgentRunStep, AnalysisTask, Dataset, User, Workspace, WorkspaceMember  # noqa: E402
from app.services import queue as task_queue  # noqa: E402
from app.services import run_lifecycle as rl  # noqa: E402
from app.services.task_service import (  # noqa: E402
    _resolve_require_sql_approval,
    approve_task,
)
from app.workers.analysis_worker import process_hitl_resume, process_task  # noqa: E402
from sqlalchemy import select  # noqa: E402


def _seed(db):
    email = f"hitl_h2_t4_{uuid4().hex[:8]}@example.com"
    user = User(email=email, password_hash=hash_password("password123"), display_name="HITL")
    db.add(user)
    db.flush()
    ws = Workspace(name="HITL H2 T4 WS", owner_user_id=user.id)
    db.add(ws)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
    ds = Dataset(
        workspace_id=ws.id,
        name="hitl_h2_t4",
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


def _set_mock_hitl() -> None:
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
        _set_mock_hitl()
        assert get_settings().analysis_runtime == "mock"
        resume_key = get_settings().hitl_resume_queue_key
        task_queue.get_redis().delete(resume_key)

        # --- mock approved → succeeded ---
        t1 = _park_approve(db, user=user, ws=ws, ds=ds, question="mock execute ok")
        plan_sql = (t1.result_json or {}).get("sql")
        assert isinstance(plan_sql, str) and plan_sql.strip()
        assert process_hitl_resume(t1.id) is True
        db.expire_all()
        t1 = db.get(AnalysisTask, t1.id)
        assert t1 is not None
        assert t1.status == "succeeded", t1.status
        rj = t1.result_json or {}
        assert rj.get("mock") is True
        assert rj.get("sql")
        hitl = (rj.get("platform") or {}).get("hitl") or {}
        assert hitl.get("phase") == "execute"
        assert hitl.get("decision") == "approved"
        assert hitl.get("executed") is True
        assert hitl.get("runtime") == "mock"
        lims = " ".join(rj.get("limitations") or []).lower()
        assert "data plane not invoked" in lims or "mock" in lims
        # Trace steps aligned with agent graph (no generate_sql)
        steps = list(
            db.scalars(
                select(AgentRunStep)
                .where(AgentRunStep.task_id == t1.id)
                .order_by(AgentRunStep.step_no)
            ).all()
        )
        names = [s.node_name for s in steps]
        assert "generate_sql" not in names, names
        assert "validate_sql" in names and "execute_sql" in names, names
        assert "load_context" in names, names
        print("OK: mock approved → succeeded (no generate_sql)")

        # --- mock snapshot mismatch → failed ---
        t2 = _park_approve(db, user=user, ws=ws, ds=ds, question="mock mismatch")
        base = dict(t2.result_json or {})
        base["sql"] = f'SELECT 42 AS tampered FROM "{ds.duckdb_table}" LIMIT 10'
        t2.result_json = base
        db.add(t2)
        db.commit()
        assert process_hitl_resume(t2.id) is True
        db.expire_all()
        t2 = db.get(AnalysisTask, t2.id)
        assert t2 is not None
        assert t2.status == "failed", t2.status
        assert t2.failure_class == rl.FAILURE_HITL_SNAPSHOT
        err = (t2.error_message or "").lower()
        assert "mismatch" in err or "diverge" in err, t2.error_message
        print("OK: mock snapshot mismatch → failed")

        # --- mock Gate reject → failed ---
        t3 = _park_approve(db, user=user, ws=ws, ds=ds, question="mock gate deny")
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
        assert "gate" in (t3.error_message or "").lower() or "rejected" in (
            t3.error_message or ""
        ).lower()
        print("OK: mock Gate reject → failed")

        print("HITL_H2_T4_OK")
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
