"""Smoke P1: Dataset ACL + Trace authorization snapshot (Shell only)."""

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
from app.services import dataset_acl_service  # noqa: E402
from app.services import permissions as perm  # noqa: E402
from app.services.permissions import PermissionError  # noqa: E402
from app.services.task_service import TaskServiceError, create_task  # noqa: E402


def main() -> None:
    get_settings.cache_clear()
    db = SessionLocal()
    try:
        owner_u = User(
            email=f"p1o_{uuid4().hex[:8]}@example.com",
            password_hash=hash_password("password123"),
            display_name="P1 Owner",
        )
        analyst_u = User(
            email=f"p1a_{uuid4().hex[:8]}@example.com",
            password_hash=hash_password("password123"),
            display_name="P1 Analyst",
        )
        viewer_u = User(
            email=f"p1v_{uuid4().hex[:8]}@example.com",
            password_hash=hash_password("password123"),
            display_name="P1 Viewer",
        )
        db.add_all([owner_u, analyst_u, viewer_u])
        db.flush()
        ws = Workspace(name="P1 WS", owner_user_id=owner_u.id)
        db.add(ws)
        db.flush()
        owner = WorkspaceMember(workspace_id=ws.id, user_id=owner_u.id, role="owner")
        analyst = WorkspaceMember(workspace_id=ws.id, user_id=analyst_u.id, role="analyst")
        viewer = WorkspaceMember(workspace_id=ws.id, user_id=viewer_u.id, role="viewer")
        db.add_all([owner, analyst, viewer])

        ds_a = Dataset(
            workspace_id=ws.id,
            name="A",
            source_type="file",
            original_filename="a.csv",
            storage_path="a",
            duckdb_table=f"ds_{uuid4().hex}",
            schema_json=[{"name": "a", "type": "INTEGER"}],
            row_count=1,
            status="ready",
            created_by=owner_u.id,
            source_config_json={},
        )
        ds_b = Dataset(
            workspace_id=ws.id,
            name="B",
            source_type="file",
            original_filename="b.csv",
            storage_path="b",
            duckdb_table=f"ds_{uuid4().hex}",
            schema_json=[{"name": "b", "type": "INTEGER"}],
            row_count=1,
            status="ready",
            created_by=owner_u.id,
            source_config_json={},
        )
        db.add_all([ds_a, ds_b])
        db.commit()
        db.refresh(owner)
        db.refresh(analyst)
        db.refresh(viewer)
        db.refresh(ds_a)
        db.refresh(ds_b)

        # --- Compat: no ACL ⇒ M5 ---
        assert perm.acl_mode_for_dataset(db, ds_a.id) == perm.ACL_MODE_DEFAULT_OPEN
        assert perm.can_read_dataset(db, viewer, ds_a, workspace=ws)
        assert not perm.can_run_dataset(db, viewer, ds_a, workspace=ws)
        assert perm.can_run_dataset(db, analyst, ds_a, workspace=ws)
        assert perm.can_run_dataset(db, owner, ds_a, workspace=ws)

        # --- Restrict ds_a: viewer read-only; analyst no grant ---
        dataset_acl_service.replace_acl(
            db,
            workspace_id=ws.id,
            dataset_id=ds_a.id,
            grants=[
                {"user_id": viewer_u.id, "can_read": True, "can_run": False},
            ],
        )
        assert perm.acl_mode_for_dataset(db, ds_a.id) == perm.ACL_MODE_RESTRICTED
        assert perm.can_read_dataset(db, viewer, ds_a, workspace=ws)
        assert not perm.can_run_dataset(db, viewer, ds_a, workspace=ws)
        assert not perm.can_read_dataset(db, analyst, ds_a, workspace=ws)
        assert not perm.can_run_dataset(db, analyst, ds_a, workspace=ws)
        # Owner bypass
        assert perm.can_read_dataset(db, owner, ds_a, workspace=ws)
        assert perm.can_run_dataset(db, owner, ds_a, workspace=ws)
        # ds_b still open
        assert perm.can_read_dataset(db, viewer, ds_b, workspace=ws)

        try:
            perm.require(analyst, perm.DATASET_GET, dataset=ds_a, workspace=ws, db=db)
            raise AssertionError("analyst should 403 get ds_a")
        except PermissionError as exc:
            assert exc.status_code == 403

        try:
            create_task(
                db,
                workspace_id=ws.id,
                user_id=analyst_u.id,
                dataset_id=ds_a.id,
                question="no run grant",
                member=analyst,
            )
            raise AssertionError("analyst create should 403")
        except TaskServiceError as exc:
            assert exc.status_code == 403

        # Grant analyst can_run on ds_a
        dataset_acl_service.replace_acl(
            db,
            workspace_id=ws.id,
            dataset_id=ds_a.id,
            grants=[
                {"user_id": viewer_u.id, "can_read": True, "can_run": False},
                {"user_id": analyst_u.id, "can_read": True, "can_run": True},
            ],
        )
        assert perm.can_run_dataset(db, analyst, ds_a, workspace=ws)

        # Authorization snapshot helper
        snap = perm.build_authorization_snapshot(
            actor_user_id=analyst_u.id,
            actor_role="analyst",
            dataset=ds_a,
            authorized_tables=[ds_a.duckdb_table],
            acl_mode=perm.acl_mode_for_dataset(db, ds_a.id),
        )
        assert snap["actor_role"] == "analyst"
        assert snap["dataset_id"] == str(ds_a.id)
        assert snap["authorized_tables"] == [ds_a.duckdb_table]
        assert snap["acl_mode"] == perm.ACL_MODE_RESTRICTED

        # Clear ACL ⇒ open again
        dataset_acl_service.replace_acl(
            db, workspace_id=ws.id, dataset_id=ds_a.id, grants=[]
        )
        assert perm.acl_mode_for_dataset(db, ds_a.id) == perm.ACL_MODE_DEFAULT_OPEN
        assert perm.can_run_dataset(db, analyst, ds_a, workspace=ws)

        print("P1_PERMISSIONS_OK")
    finally:
        db.close()


if __name__ == "__main__":
    main()
