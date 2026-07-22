"""Smoke M5: thin resource permission matrix (no IAM)."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import Dataset, User, Workspace, WorkspaceMember  # noqa: E402
from app.services import permissions as perm  # noqa: E402
from app.services.permissions import PermissionError  # noqa: E402
from app.services.task_service import TaskServiceError, create_task  # noqa: E402


def main() -> None:
    get_settings.cache_clear()
    db = SessionLocal()
    try:
        email = f"m5_{uuid4().hex[:8]}@example.com"
        user = User(
            email=email,
            password_hash=hash_password("password123"),
            display_name="M5",
        )
        db.add(user)
        db.flush()
        ws = Workspace(name="M5 WS", owner_user_id=user.id)
        db.add(ws)
        db.flush()
        owner = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner")
        db.add(owner)

        viewer_user = User(
            email=f"m5v_{uuid4().hex[:8]}@example.com",
            password_hash=hash_password("password123"),
            display_name="M5 Viewer",
        )
        db.add(viewer_user)
        db.flush()
        viewer = WorkspaceMember(
            workspace_id=ws.id, user_id=viewer_user.id, role="viewer"
        )
        db.add(viewer)

        ds = Dataset(
            workspace_id=ws.id,
            name="m5",
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
        db.commit()
        db.refresh(owner)
        db.refresh(viewer)
        db.refresh(ds)

        assert perm.can(owner, perm.DATASET_CREATE_FILE)
        assert perm.can(owner, perm.DATASET_BIND_POSTGRES_RO)
        assert perm.can(owner, perm.RUN_CREATE, dataset=ds)
        assert not perm.can(viewer, perm.DATASET_CREATE_FILE)
        assert not perm.can(viewer, perm.DATASET_BIND_POSTGRES_RO)
        assert not perm.can(viewer, perm.RUN_CREATE, dataset=ds)
        assert perm.can(viewer, perm.DATASET_GET, dataset=ds)
        assert perm.can(viewer, perm.RUN_GET)
        assert perm.can(viewer, perm.RUN_EXECUTION)

        try:
            perm.require(viewer, perm.RUN_CREATE, dataset=ds)
            raise AssertionError("viewer should not create run")
        except PermissionError as exc:
            assert exc.status_code == 403

        try:
            create_task(
                db,
                workspace_id=ws.id,
                user_id=viewer_user.id,
                dataset_id=ds.id,
                question="should fail",
                member=viewer,
            )
            raise AssertionError("create_task should 403 for viewer")
        except TaskServiceError as exc:
            assert exc.status_code == 403

        # Owner still can enqueue (may fail Redis — treat enqueue as optional)
        try:
            task = create_task(
                db,
                workspace_id=ws.id,
                user_id=user.id,
                dataset_id=ds.id,
                question="owner ok",
                member=owner,
            )
            assert task.status in {"pending", "failed"}
        except TaskServiceError as exc:
            # Redis down → enqueue_error is OK for permission smoke
            assert exc.status_code in {403, 503}
            if exc.status_code == 403:
                raise

        print("M5 smoke OK")
    finally:
        db.close()


if __name__ == "__main__":
    main()
