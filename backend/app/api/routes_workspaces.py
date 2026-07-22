from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_workspace_member
from app.core.db import get_db
from app.models import User, WorkspaceMember
from app.schemas.workspace import WorkspaceDetailOut, WorkspaceListOut, WorkspaceUpdateRequest
from app.services import permissions as perm
from app.services import workspace_service
from app.services.permissions import PermissionError

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


@router.get("", response_model=WorkspaceListOut)
def list_workspaces(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceListOut:
    rows = workspace_service.list_memberships_for_user(db, user_id=user.id)
    items = [
        WorkspaceDetailOut(
            id=ws.id,
            name=ws.name,
            owner_user_id=ws.owner_user_id,
            role=role,
            created_at=ws.created_at,
        )
        for ws, role in rows
    ]
    return WorkspaceListOut(items=items)


@router.get("/{workspace_id}", response_model=WorkspaceDetailOut)
def get_workspace(
    workspace_id: UUID,
    ctx: tuple[User, WorkspaceMember] = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> WorkspaceDetailOut:
    _user, member = ctx
    workspace = workspace_service.get_workspace(db, workspace_id=workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return WorkspaceDetailOut(
        id=workspace.id,
        name=workspace.name,
        owner_user_id=workspace.owner_user_id,
        role=member.role,
        created_at=workspace.created_at,
    )


@router.patch("/{workspace_id}", response_model=WorkspaceDetailOut)
def update_workspace(
    workspace_id: UUID,
    body: WorkspaceUpdateRequest,
    ctx: tuple[User, WorkspaceMember] = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> WorkspaceDetailOut:
    _user, member = ctx
    try:
        perm.require(member, perm.WORKSPACE_UPDATE)
    except PermissionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    workspace = workspace_service.get_workspace(db, workspace_id=workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    workspace.name = body.name.strip()
    db.add(workspace)
    db.commit()
    db.refresh(workspace)

    return WorkspaceDetailOut(
        id=workspace.id,
        name=workspace.name,
        owner_user_id=workspace.owner_user_id,
        role=member.role,
        created_at=workspace.created_at,
    )
