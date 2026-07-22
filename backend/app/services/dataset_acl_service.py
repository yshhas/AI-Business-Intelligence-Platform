"""P1 Dataset ACL orchestration — owner grants only (Shell)."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Dataset, DatasetAcl, WorkspaceMember
from app.services import permissions as perm
from app.services.dataset_service import DatasetServiceError, get_dataset


def list_acl(db: Session, *, workspace_id: UUID, dataset_id: UUID) -> list[DatasetAcl]:
    dataset = get_dataset(db, workspace_id=workspace_id, dataset_id=dataset_id)
    if dataset is None:
        raise DatasetServiceError("Dataset not found", status_code=404)
    return list(
        db.scalars(
            select(DatasetAcl)
            .where(
                DatasetAcl.dataset_id == dataset_id,
                DatasetAcl.workspace_id == workspace_id,
            )
            .order_by(DatasetAcl.created_at.asc())
        ).all()
    )


def replace_acl(
    db: Session,
    *,
    workspace_id: UUID,
    dataset_id: UUID,
    grants: list[dict],
) -> list[DatasetAcl]:
    """Replace all ACL rows for a dataset. Empty grants ⇒ default_open (M5)."""
    dataset = get_dataset(db, workspace_id=workspace_id, dataset_id=dataset_id)
    if dataset is None:
        raise DatasetServiceError("Dataset not found", status_code=404)

    # Validate users are workspace members
    member_ids = {
        m.user_id
        for m in db.scalars(
            select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id)
        ).all()
    }

    cleaned: list[tuple[UUID, bool, bool, list[str] | None]] = []
    seen: set[UUID] = set()
    for g in grants:
        uid = g.get("user_id")
        if uid is None:
            raise DatasetServiceError("grant.user_id required", status_code=400)
        uid = UUID(str(uid))
        if uid in seen:
            raise DatasetServiceError(f"duplicate user_id in grants: {uid}", status_code=400)
        seen.add(uid)
        if uid not in member_ids:
            raise DatasetServiceError(
                f"user {uid} is not a member of this workspace",
                status_code=400,
            )
        can_read = bool(g.get("can_read", True))
        can_run = bool(g.get("can_run", False))
        if can_run and not can_read:
            # run implies read for Demo honesty
            can_read = True
        tables = g.get("tables")
        tables_json: list[str] | None = None
        if tables is not None:
            if not isinstance(tables, list):
                raise DatasetServiceError("grant.tables must be a list", status_code=400)
            tables_json = [str(t).strip() for t in tables if str(t).strip()]
            if not tables_json:
                tables_json = None
        cleaned.append((uid, can_read, can_run, tables_json))

    db.execute(delete(DatasetAcl).where(DatasetAcl.dataset_id == dataset_id))
    db.flush()
    rows: list[DatasetAcl] = []
    for uid, can_read, can_run, tables_json in cleaned:
        row = DatasetAcl(
            id=uuid4(),
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            user_id=uid,
            can_read=can_read,
            can_run=can_run,
            tables_json=tables_json,
        )
        db.add(row)
        rows.append(row)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def filter_readable_datasets(
    db: Session,
    *,
    datasets: list[Dataset],
    member: WorkspaceMember,
    workspace=None,
) -> list[Dataset]:
    return [
        d
        for d in datasets
        if perm.can_read_dataset(db, member, d, workspace=workspace)
    ]
