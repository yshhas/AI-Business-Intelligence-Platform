"""Smoke E3: stale reclaim + in-flight / queue depth enqueue guards.

Requires Postgres + Redis. Does not require a long-running worker process.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

# Force tight caps + isolated queue for this process before Settings is cached
os.environ["RUN_MAX_IN_FLIGHT"] = "1"
os.environ["ANALYSIS_QUEUE_MAX_DEPTH"] = "2"
os.environ["STALE_RUNNING_SECONDS"] = "30"
os.environ["ANALYSIS_QUEUE_KEY"] = f"aibi:e3_smoke_{uuid4().hex[:8]}"

from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import AnalysisTask, Dataset, User, Workspace, WorkspaceMember  # noqa: E402
from app.services import queue as task_queue  # noqa: E402
from app.services import run_lifecycle as rl  # noqa: E402
from app.services import runtime_essentials as rt  # noqa: E402
from app.services.task_service import TaskServiceError, create_task  # noqa: E402


def main() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.run_max_in_flight == 1
    assert settings.analysis_queue_max_depth == 2
    assert settings.stale_running_seconds == 30

    db = SessionLocal()
    try:
        email = f"e3_{uuid4().hex[:8]}@example.com"
        user = User(
            email=email,
            password_hash=hash_password("password123"),
            display_name="E3",
        )
        db.add(user)
        db.flush()
        ws = Workspace(name="E3 WS", owner_user_id=user.id)
        db.add(ws)
        db.flush()
        db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
        ds = Dataset(
            workspace_id=ws.id,
            name="e3",
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
        db.commit()
        db.refresh(user)
        db.refresh(ws)
        db.refresh(ds)

        # --- Stale reclaim ---
        orphan = AnalysisTask(
            workspace_id=ws.id,
            dataset_id=ds.id,
            user_id=user.id,
            question="orphan",
            status="running",
            started_at=datetime.now(UTC) - timedelta(seconds=120),
            last_heartbeat_at=datetime.now(UTC) - timedelta(seconds=120),
            timeout_seconds=120,
        )
        db.add(orphan)
        db.commit()
        db.refresh(orphan)
        n = rt.reclaim_stale_running(db, settings)
        assert n >= 1
        db.refresh(orphan)
        assert orphan.status == "failed"
        assert orphan.failure_class == rl.FAILURE_RUNTIME_RECLAIMED
        assert orphan.finished_at is not None
        platform = (orphan.result_json or {}).get("platform") or {}
        assert (platform.get("run") or {}).get("failure_class") == rl.FAILURE_RUNTIME_RECLAIMED

        # Fresh running should NOT reclaim
        fresh = AnalysisTask(
            workspace_id=ws.id,
            dataset_id=ds.id,
            user_id=user.id,
            question="fresh",
            status="running",
            started_at=datetime.now(UTC),
            last_heartbeat_at=datetime.now(UTC),
            timeout_seconds=120,
        )
        db.add(fresh)
        db.commit()
        n2 = rt.reclaim_stale_running(db, settings)
        db.refresh(fresh)
        assert fresh.status == "running"
        assert n2 == 0

        # --- In-flight enqueue reject (running=1 already: fresh) ---
        try:
            create_task(
                db,
                workspace_id=ws.id,
                user_id=user.id,
                dataset_id=ds.id,
                question="should reject inflight",
                member_role="owner",
            )
            raise AssertionError("expected capacity reject for in-flight")
        except TaskServiceError as exc:
            assert exc.status_code == 429
            assert "in-flight" in str(exc).lower() or "capacity" in str(exc).lower()

        # Clear running so queue-depth path can be tested
        fresh.status = "succeeded"
        fresh.finished_at = datetime.now(UTC)
        db.add(fresh)
        db.commit()

        # --- Queue depth: fill Redis list without consuming ---
        settings = get_settings()
        r = task_queue.get_redis()
        r.delete(settings.analysis_queue_key)
        for _ in range(settings.analysis_queue_max_depth):
            task_queue.enqueue_task(uuid4())
        depth = task_queue.queue_length()
        assert depth >= settings.analysis_queue_max_depth, (
            f"expected depth>={settings.analysis_queue_max_depth}, got {depth} "
            f"key={settings.analysis_queue_key}"
        )
        try:
            create_task(
                db,
                workspace_id=ws.id,
                user_id=user.id,
                dataset_id=ds.id,
                question="should reject queue depth",
                member_role="owner",
            )
            raise AssertionError("expected capacity reject for queue depth")
        except TaskServiceError as exc:
            assert exc.status_code == 429
            assert "queue" in str(exc).lower()

        r.delete(settings.analysis_queue_key)

        print("E3 smoke OK: reclaim + inflight reject + queue depth reject")
    finally:
        db.close()


if __name__ == "__main__":
    main()
