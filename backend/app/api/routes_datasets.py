from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import require_workspace_member
from app.core.db import get_db
from app.models import User, Workspace, WorkspaceMember
from app.schemas.dataset import (
    DatasetAclListOut,
    DatasetAclOut,
    DatasetAclReplaceIn,
    DatasetListOut,
    DatasetOut,
    MysqlRoBindIn,
    PostgresRoBindIn,
    PreviewOut,
)
from app.services import dataset_acl_service, dataset_service, permissions as perm
from app.services.dataset_service import DatasetServiceError
from app.services.permissions import PermissionError

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/datasets",
    tags=["datasets"],
)


def _http_error(exc: DatasetServiceError | PermissionError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _workspace(db: Session, workspace_id: UUID) -> Workspace | None:
    return db.get(Workspace, workspace_id)


@router.get("", response_model=DatasetListOut)
def list_datasets(
    workspace_id: UUID,
    ctx: tuple[User, WorkspaceMember] = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> DatasetListOut:
    _user, member = ctx
    try:
        perm.require(member, perm.DATASET_LIST)
    except PermissionError as exc:
        raise _http_error(exc) from exc
    ws = _workspace(db, workspace_id)
    items = dataset_service.list_datasets(
        db, workspace_id=workspace_id, member=member, workspace=ws
    )
    return DatasetListOut(items=[DatasetOut.model_validate(d) for d in items])


@router.post("/upload", response_model=DatasetOut, status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    workspace_id: UUID,
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    ctx: tuple[User, WorkspaceMember] = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> DatasetOut:
    user, member = ctx
    try:
        perm.require(member, perm.DATASET_CREATE_FILE)
        dataset = await dataset_service.create_dataset_from_upload(
            db,
            workspace_id=workspace_id,
            user_id=user.id,
            upload=file,
            name=name,
        )
    except PermissionError as exc:
        raise _http_error(exc) from exc
    except DatasetServiceError as exc:
        raise _http_error(exc) from exc
    return DatasetOut.model_validate(dataset)


@router.post(
    "/postgres-ro",
    response_model=DatasetOut,
    status_code=status.HTTP_201_CREATED,
)
def bind_postgres_ro_dataset(
    workspace_id: UUID,
    body: PostgresRoBindIn,
    ctx: tuple[User, WorkspaceMember] = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> DatasetOut:
    """M3 thin bind: Workspace → readonly Postgres source (DSN from env)."""
    user, member = ctx
    try:
        perm.require(member, perm.DATASET_BIND_POSTGRES_RO)
        dataset = dataset_service.create_dataset_from_postgres_ro(
            db,
            workspace_id=workspace_id,
            user_id=user.id,
            name=body.name,
            tables=body.tables,
        )
    except PermissionError as exc:
        raise _http_error(exc) from exc
    except DatasetServiceError as exc:
        raise _http_error(exc) from exc
    return DatasetOut.model_validate(dataset)


@router.post(
    "/mysql-ro",
    response_model=DatasetOut,
    status_code=status.HTTP_201_CREATED,
)
def bind_mysql_ro_dataset(
    workspace_id: UUID,
    body: MysqlRoBindIn,
    ctx: tuple[User, WorkspaceMember] = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> DatasetOut:
    """Wave 3 thin bind: Workspace → readonly MySQL (DSN from MYSQL_RO_DSN)."""
    user, member = ctx
    try:
        # Same mutator gate as postgres_ro — not a separate IAM product
        perm.require(member, perm.DATASET_BIND_POSTGRES_RO)
        dataset = dataset_service.create_dataset_from_mysql_ro(
            db,
            workspace_id=workspace_id,
            user_id=user.id,
            name=body.name,
            tables=body.tables,
        )
    except PermissionError as exc:
        raise _http_error(exc) from exc
    except DatasetServiceError as exc:
        raise _http_error(exc) from exc
    return DatasetOut.model_validate(dataset)


@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(
    workspace_id: UUID,
    dataset_id: UUID,
    ctx: tuple[User, WorkspaceMember] = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> DatasetOut:
    _user, member = ctx
    ws = _workspace(db, workspace_id)
    dataset = dataset_service.get_dataset(
        db, workspace_id=workspace_id, dataset_id=dataset_id
    )
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    try:
        perm.require(member, perm.DATASET_GET, dataset=dataset, workspace=ws, db=db)
    except PermissionError as exc:
        raise _http_error(exc) from exc
    return DatasetOut.model_validate(dataset)


@router.get("/{dataset_id}/preview", response_model=PreviewOut)
def preview_dataset(
    workspace_id: UUID,
    dataset_id: UUID,
    limit: int = 50,
    ctx: tuple[User, WorkspaceMember] = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> PreviewOut:
    _user, member = ctx
    ws = _workspace(db, workspace_id)
    dataset = dataset_service.get_dataset(
        db, workspace_id=workspace_id, dataset_id=dataset_id
    )
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    try:
        perm.require(member, perm.DATASET_PREVIEW, dataset=dataset, workspace=ws, db=db)
        data = dataset_service.preview_dataset(
            db,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            limit=limit,
        )
    except PermissionError as exc:
        raise _http_error(exc) from exc
    except DatasetServiceError as exc:
        raise _http_error(exc) from exc
    return PreviewOut(**data)


@router.get("/{dataset_id}/acl", response_model=DatasetAclListOut)
def get_dataset_acl(
    workspace_id: UUID,
    dataset_id: UUID,
    ctx: tuple[User, WorkspaceMember] = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> DatasetAclListOut:
    """P1: list ACL grants (owner only). Empty list ⇒ default_open (M5)."""
    _user, member = ctx
    ws = _workspace(db, workspace_id)
    try:
        perm.require(member, perm.DATASET_ACL_GET, workspace=ws)
        rows = dataset_acl_service.list_acl(
            db, workspace_id=workspace_id, dataset_id=dataset_id
        )
    except PermissionError as exc:
        raise _http_error(exc) from exc
    except DatasetServiceError as exc:
        raise _http_error(exc) from exc
    return DatasetAclListOut(items=[DatasetAclOut.model_validate(r) for r in rows])


@router.put("/{dataset_id}/acl", response_model=DatasetAclListOut)
def put_dataset_acl(
    workspace_id: UUID,
    dataset_id: UUID,
    body: DatasetAclReplaceIn,
    ctx: tuple[User, WorkspaceMember] = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> DatasetAclListOut:
    """P1: replace ACL grants (owner only). grants=[] clears ACL → M5 open."""
    _user, member = ctx
    ws = _workspace(db, workspace_id)
    try:
        perm.require(member, perm.DATASET_ACL_PUT, workspace=ws)
        rows = dataset_acl_service.replace_acl(
            db,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            grants=[g.model_dump() for g in body.grants],
        )
    except PermissionError as exc:
        raise _http_error(exc) from exc
    except DatasetServiceError as exc:
        raise _http_error(exc) from exc
    return DatasetAclListOut(items=[DatasetAclOut.model_validate(r) for r in rows])
