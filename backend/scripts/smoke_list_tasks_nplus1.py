"""P1.5 smoke: list_tasks visibility filter uses batched queries (no per-row N+1)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from sqlalchemy import event, select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import (  # noqa: E402
    AnalysisTask,
    Dataset,
    DatasetAcl,
    User,
    Workspace,
    WorkspaceMember,
)
from app.services.task_service import list_tasks  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        suffix = uuid4().hex[:8]
        owner = User(
            email=f"list_n1_owner_{suffix}@example.com",
            password_hash=hash_password("password123"),
            display_name="Owner",
        )
        viewer = User(
            email=f"list_n1_viewer_{suffix}@example.com",
            password_hash=hash_password("password123"),
            display_name="Viewer",
        )
        db.add_all([owner, viewer])
        db.flush()

        ws = Workspace(name=f"list-n1-{suffix}", owner_user_id=owner.id)
        db.add(ws)
        db.flush()
        db.add_all(
            [
                WorkspaceMember(workspace_id=ws.id, user_id=owner.id, role="owner"),
                WorkspaceMember(workspace_id=ws.id, user_id=viewer.id, role="viewer"),
            ]
        )
        db.flush()

        ds = Dataset(
            workspace_id=ws.id,
            name="n1-ds",
            source_type="file",
            original_filename="n1.csv",
            storage_path=f"/tmp/n1-{suffix}.csv",
            duckdb_table=f"ds_n1_{suffix}",
            schema_json=[{"name": "id", "type": "INTEGER"}],
            row_count=1,
            status="ready",
            created_by=owner.id,
            source_config_json={},
        )
        db.add(ds)
        db.flush()
        db.add(
            DatasetAcl(
                workspace_id=ws.id,
                dataset_id=ds.id,
                user_id=viewer.id,
                can_read=True,
                can_run=False,
            )
        )
        db.flush()

        n = 25
        for i in range(n):
            db.add(
                AnalysisTask(
                    workspace_id=ws.id,
                    dataset_id=ds.id,
                    user_id=owner.id,
                    question=f"q{i}",
                    status="succeeded",
                )
            )
        db.commit()

        member = db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == ws.id,
                WorkspaceMember.user_id == viewer.id,
            )
        ).scalar_one()

        statements: list[str] = []
        eng = db.get_bind()

        def _count(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
            statements.append(str(statement))

        event.listen(eng, "before_cursor_execute", _count)
        try:
            items = list_tasks(
                db,
                workspace_id=ws.id,
                limit=50,
                member=member,
                user_id=viewer.id,
            )
        finally:
            event.remove(eng, "before_cursor_execute", _count)

        assert len(items) == n, f"expected {n} visible tasks, got {len(items)}"
        qn = len(statements)
        # Batched path: tasks + workspace + datasets IN + ACL group + ACL entries (~5).
        assert qn <= 8, f"too many queries for list_tasks ({qn}): {statements}"
        print(f"LIST_TASKS_QUERY_COUNT {qn}")
        print("LIST_TASKS_NPLUS1_OK")
    finally:
        db.close()


if __name__ == "__main__":
    main()
