from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User, Workspace, WorkspaceMember


def create_default_workspace(db: Session, *, user: User) -> tuple[Workspace, WorkspaceMember]:
    workspace = Workspace(name=f"{user.display_name}'s Workspace", owner_user_id=user.id)
    db.add(workspace)
    db.flush()

    member = WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner")
    db.add(member)
    db.flush()
    return workspace, member


def list_memberships_for_user(db: Session, *, user_id: UUID) -> list[tuple[Workspace, str]]:
    stmt = (
        select(Workspace, WorkspaceMember.role)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user_id)
        .order_by(Workspace.created_at.asc())
    )
    return list(db.execute(stmt).all())


def get_membership(
    db: Session, *, workspace_id: UUID, user_id: UUID
) -> WorkspaceMember | None:
    stmt = select(WorkspaceMember).where(
        WorkspaceMember.workspace_id == workspace_id,
        WorkspaceMember.user_id == user_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def get_workspace(db: Session, *, workspace_id: UUID) -> Workspace | None:
    return db.get(Workspace, workspace_id)
