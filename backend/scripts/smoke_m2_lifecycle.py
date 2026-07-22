"""Smoke: cancel pending task + timeout path (requires Redis + Postgres)."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.models import AnalysisTask, Dataset, User, Workspace, WorkspaceMember  # noqa: E402
from app.services import run_lifecycle as rl  # noqa: E402
from app.services.task_service import cancel_task, create_task  # noqa: E402
from app.workers.analysis_worker import process_task  # noqa: E402
from app.core.security import hash_password  # noqa: E402


def main() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.run_timeout_seconds == 120 or settings.run_timeout_seconds > 0

    db = SessionLocal()
    try:
        email = f"m2_{uuid4().hex[:8]}@example.com"
        user = User(
            email=email,
            password_hash=hash_password("password123"),
            display_name="M2",
        )
        db.add(user)
        db.flush()
        ws = Workspace(name="M2 WS", owner_user_id=user.id)
        db.add(ws)
        db.flush()
        db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
        # Minimal fake ready dataset row pointing at nothing — cancel pending needs no duckdb
        ds = Dataset(
            workspace_id=ws.id,
            name="m2",
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
        db.commit()
        db.refresh(user)
        db.refresh(ws)
        db.refresh(ds)

        # --- pending cancel ---
        task = create_task(
            db,
            workspace_id=ws.id,
            user_id=user.id,
            dataset_id=ds.id,
            question="will cancel",
        )
        assert task.status == "pending"
        assert task.timeout_seconds == settings.run_timeout_seconds
        cancelled = cancel_task(
            db,
            workspace_id=ws.id,
            task_id=task.id,
            user_id=user.id,
            member_role="owner",
        )
        assert cancelled.status == "cancelled"
        assert cancelled.failure_class == rl.FAILURE_CANCELLED
        process_task(task.id)  # should no-op
        db.refresh(cancelled)
        assert cancelled.status == "cancelled"
        print("CANCEL_PENDING_OK")

        # --- timeout with mock runtime + tiny budget ---
        task2 = AnalysisTask(
            workspace_id=ws.id,
            dataset_id=ds.id,
            user_id=user.id,
            question="timeout me",
            status="pending",
            timeout_seconds=1,
            cancel_requested=False,
        )
        db.add(task2)
        db.commit()
        db.refresh(task2)

        import app.workers.analysis_worker as worker_mod

        orig = worker_mod.run_mock_analysis

        def slow_mock(db_sess, t, **kwargs):
            time.sleep(3)
            return orig(db_sess, t, **kwargs)

        worker_mod.run_mock_analysis = slow_mock  # type: ignore[assignment]
        from app.core import config as cfg

        real_get = cfg.get_settings

        def fake_settings():
            base = real_get()

            class Overlay:
                def __getattr__(self, name):
                    if name == "analysis_runtime":
                        return "mock"
                    return getattr(base, name)

            return Overlay()

        try:
            cfg.get_settings = fake_settings  # type: ignore[assignment]
            worker_mod.get_settings = fake_settings  # type: ignore[assignment]
            process_task(task2.id)
        finally:
            worker_mod.run_mock_analysis = orig  # type: ignore[assignment]
            cfg.get_settings = real_get  # type: ignore[assignment]
            worker_mod.get_settings = real_get  # type: ignore[assignment]

        db.expire_all()
        t2 = db.get(AnalysisTask, task2.id)
        assert t2 is not None
        assert t2.status == "timed_out", (t2.status, t2.error_message)
        assert t2.failure_class == rl.FAILURE_TIMEOUT
        print("TIMEOUT_OK")
        print("M2_LIFECYCLE_OK")
    finally:
        db.close()


if __name__ == "__main__":
    main()
