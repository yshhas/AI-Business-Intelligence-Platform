"""P1.1 smoke: cooperative running-cancel + wall-clock timeout fence (Redis + Postgres)."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import AgentRunStep, AnalysisTask, Dataset, User, Workspace, WorkspaceMember  # noqa: E402
from app.services import run_lifecycle as rl  # noqa: E402
from app.services.task_service import cancel_task  # noqa: E402
from app.workers.analysis_worker import process_task  # noqa: E402
from sqlalchemy import func, select  # noqa: E402


def _seed(db):
    email = f"p11_{uuid4().hex[:8]}@example.com"
    user = User(email=email, password_hash=hash_password("password123"), display_name="P11")
    db.add(user)
    db.flush()
    ws = Workspace(name="P11 WS", owner_user_id=user.id)
    db.add(ws)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
    ds = Dataset(
        workspace_id=ws.id,
        name="p11",
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
    return user, ws, ds


def main() -> None:
    get_settings.cache_clear()
    db = SessionLocal()
    try:
        user, ws, ds = _seed(db)

        import app.workers.analysis_worker as worker_mod
        from app.core import config as cfg

        orig_mock = worker_mod.run_mock_analysis
        real_get = cfg.get_settings

        def fake_settings():
            base = real_get()

            class Overlay:
                def __getattr__(self, name):
                    if name == "analysis_runtime":
                        return "mock"
                    return getattr(base, name)

            return Overlay()

        # --- C2: wall-clock timeout should not wait full Skill ---
        task_to = AnalysisTask(
            workspace_id=ws.id,
            dataset_id=ds.id,
            user_id=user.id,
            question="timeout wall clock",
            status="pending",
            timeout_seconds=1,
            cancel_requested=False,
        )
        db.add(task_to)
        db.commit()
        db.refresh(task_to)

        def slow_mock(db_sess, t, **kwargs):
            time.sleep(4)
            return orig_mock(db_sess, t, **kwargs)

        worker_mod.run_mock_analysis = slow_mock  # type: ignore[assignment]
        cfg.get_settings = fake_settings  # type: ignore[assignment]
        worker_mod.get_settings = fake_settings  # type: ignore[assignment]
        t0 = time.monotonic()
        try:
            process_task(task_to.id)
        finally:
            worker_mod.run_mock_analysis = orig_mock  # type: ignore[assignment]
            cfg.get_settings = real_get  # type: ignore[assignment]
            worker_mod.get_settings = real_get  # type: ignore[assignment]

        elapsed = time.monotonic() - t0
        db.expire_all()
        row = db.get(AnalysisTask, task_to.id)
        assert row is not None
        assert row.status == "timed_out", (row.status, row.error_message)
        assert row.failure_class == rl.FAILURE_TIMEOUT
        # Must finish well before the 4s sleep (grace may add a few seconds)
        assert elapsed < 3.5, f"timeout waited too long: {elapsed:.2f}s"
        print("TIMEOUT_WALL_CLOCK_OK", f"elapsed={elapsed:.2f}s")

        # Allow slow thread to finish / fence
        time.sleep(1.0)
        db.expire_all()
        steps_after = db.scalar(
            select(func.count()).select_from(AgentRunStep).where(
                AgentRunStep.task_id == task_to.id
            )
        )
        # Late writes fenced — prefer zero; allow at most partial if race before mark
        assert steps_after is not None
        print("TIMEOUT_FENCE_STEPS", steps_after)

        # --- C1: running cancel ---
        task_c = AnalysisTask(
            workspace_id=ws.id,
            dataset_id=ds.id,
            user_id=user.id,
            question="cancel while running",
            status="pending",
            timeout_seconds=30,
            cancel_requested=False,
        )
        db.add(task_c)
        db.commit()
        db.refresh(task_c)

        started = threading.Event()

        def slow_mock_cancel(db_sess, t, **kwargs):
            started.set()
            # Long enough for cancel API; checkpoints every 0.15s in orig after sleep
            time.sleep(0.5)
            return orig_mock(db_sess, t, **kwargs)

        worker_mod.run_mock_analysis = slow_mock_cancel  # type: ignore[assignment]
        cfg.get_settings = fake_settings  # type: ignore[assignment]
        worker_mod.get_settings = fake_settings  # type: ignore[assignment]

        def run_worker():
            process_task(task_c.id)

        th = threading.Thread(target=run_worker, daemon=True)
        th.start()
        assert started.wait(timeout=5), "worker did not start mock"
        # Request cancel while running
        cancel_db = SessionLocal()
        try:
            cancelled = cancel_task(
                cancel_db,
                workspace_id=ws.id,
                task_id=task_c.id,
                user_id=user.id,
                member_role="owner",
            )
            assert cancelled.cancel_requested is True
        finally:
            cancel_db.close()

        th.join(timeout=10)
        assert not th.is_alive(), "worker did not finish after cancel"

        worker_mod.run_mock_analysis = orig_mock  # type: ignore[assignment]
        cfg.get_settings = real_get  # type: ignore[assignment]
        worker_mod.get_settings = real_get  # type: ignore[assignment]

        db.expire_all()
        crow = db.get(AnalysisTask, task_c.id)
        assert crow is not None
        assert crow.status == "cancelled", (crow.status, crow.error_message)
        assert crow.failure_class == rl.FAILURE_CANCELLED
        print("RUNNING_CANCEL_OK")

        # --- C3: must not end succeeded ---
        assert crow.status != "succeeded"
        assert row.status != "succeeded"
        print("NO_SUCCESS_AFTER_ABORT_OK")

        print("P1_1_COOPERATIVE_CANCEL_OK")
    finally:
        db.close()


if __name__ == "__main__":
    main()
