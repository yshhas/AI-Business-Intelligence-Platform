from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import require_workspace_member
from app.core.config import get_settings
from app.core.db import get_db
from app.models import User, Workspace, WorkspaceMember
from app.schemas.task import (
    ArtifactListOut,
    ArtifactOut,
    ExecutionTraceOut,
    StepListOut,
    StepOut,
    TaskCreateRequest,
    TaskListOut,
    TaskOut,
)
from app.services import artifact_service
from app.services import dataset_service
from app.services import permissions as perm
from app.services import task_events
from app.services import task_service
from app.services.permissions import PermissionError
from app.services.task_service import TaskServiceError

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/tasks",
    tags=["tasks"],
)


def _http_error(exc: TaskServiceError | PermissionError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _require_task_access(
    db: Session,
    *,
    workspace_id: UUID,
    task_id: UUID,
    member: WorkspaceMember,
    user: User,
    action: str,
):
    task = task_service.get_task(db, workspace_id=workspace_id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    dataset = dataset_service.get_dataset(
        db, workspace_id=workspace_id, dataset_id=task.dataset_id
    )
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    ws = db.get(Workspace, workspace_id)
    try:
        perm.require(
            member,
            action,
            task=task,
            dataset=dataset,
            workspace=ws,
            user_id=user.id,
            db=db,
        )
    except PermissionError as exc:
        raise _http_error(exc) from exc
    return task


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    workspace_id: UUID,
    body: TaskCreateRequest,
    ctx: tuple[User, WorkspaceMember] = Depends(require_workspace_member),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> TaskOut:
    user, member = ctx
    try:
        from app.services.rate_limit import RateLimitExceeded, check_task_create_rate_limit

        check_task_create_rate_limit(user_id=user.id, workspace_id=workspace_id)
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    try:
        task = task_service.create_task(
            db,
            workspace_id=workspace_id,
            user_id=user.id,
            dataset_id=body.dataset_id,
            question=body.question,
            member_role=member.role,
            member=member,
            skill_id=body.skill_id,
            idempotency_key=idempotency_key,
        )
    except TaskServiceError as exc:
        raise _http_error(exc) from exc
    return TaskOut.model_validate(task)


@router.get("", response_model=TaskListOut)
def list_tasks(
    workspace_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    skill_id: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    policy_denied: bool | None = Query(default=None),
    failure_class: str | None = Query(default=None),
    ctx: tuple[User, WorkspaceMember] = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> TaskListOut:
    _user, member = ctx
    try:
        perm.require(member, perm.RUN_LIST)
    except PermissionError as exc:
        raise _http_error(exc) from exc
    items = task_service.list_tasks(
        db,
        workspace_id=workspace_id,
        limit=limit,
        status=status_filter,
        skill_id=skill_id,
        source_type=source_type,
        policy_denied=policy_denied,
        failure_class=failure_class,
        member=member,
        user_id=_user.id,
    )
    return TaskListOut(items=[TaskOut.model_validate(t) for t in items])


@router.get("/{task_id}", response_model=TaskOut)
def get_task(
    workspace_id: UUID,
    task_id: UUID,
    ctx: tuple[User, WorkspaceMember] = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> TaskOut:
    user, member = ctx
    task = _require_task_access(
        db,
        workspace_id=workspace_id,
        task_id=task_id,
        member=member,
        user=user,
        action=perm.RUN_GET,
    )
    return TaskOut.model_validate(task)


@router.get("/{task_id}/execution", response_model=ExecutionTraceOut)
def get_task_execution(
    workspace_id: UUID,
    task_id: UUID,
    ctx: tuple[User, WorkspaceMember] = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> ExecutionTraceOut:
    """M4: Execution Trace for this Run (not an Audit product endpoint)."""
    user, member = ctx
    _require_task_access(
        db,
        workspace_id=workspace_id,
        task_id=task_id,
        member=member,
        user=user,
        action=perm.RUN_EXECUTION,
    )
    trace = task_service.get_execution_trace(
        db, workspace_id=workspace_id, task_id=task_id
    )
    if trace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return ExecutionTraceOut.model_validate(trace)


@router.get("/{task_id}/artifacts", response_model=ArtifactListOut)
def list_task_artifacts(
    workspace_id: UUID,
    task_id: UUID,
    type_filter: str | None = Query(default=None, alias="type"),
    ctx: tuple[User, WorkspaceMember] = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> ArtifactListOut:
    """M6: list Artifact metadata for a Run (inherits Run visibility)."""
    user, member = ctx
    task = _require_task_access(
        db,
        workspace_id=workspace_id,
        task_id=task_id,
        member=member,
        user=user,
        action=perm.ARTIFACT_LIST,
    )
    rows = artifact_service.list_for_task(
        db, workspace_id=workspace_id, task_id=task_id
    )
    if type_filter:
        rows = [r for r in rows if r.type == type_filter]
    return ArtifactListOut(
        items=[
            ArtifactOut(
                id=r.id,
                task_id=r.task_id,
                workspace_id=r.workspace_id,
                type=r.type,
                status=r.status,
                content_ref=dict(r.content_ref or {}),
                title=r.title,
                skill_id=r.skill_id,
                created_at=r.created_at,
                lineage=artifact_service.lineage_for(task, r),
            )
            for r in rows
        ]
    )


@router.get("/{task_id}/artifacts/{artifact_id}", response_model=ArtifactOut)
def get_task_artifact(
    workspace_id: UUID,
    task_id: UUID,
    artifact_id: UUID,
    ctx: tuple[User, WorkspaceMember] = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> ArtifactOut:
    """M6: get one Artifact (metadata + payload via content_ref). No global /artifacts."""
    user, member = ctx
    task = _require_task_access(
        db,
        workspace_id=workspace_id,
        task_id=task_id,
        member=member,
        user=user,
        action=perm.ARTIFACT_GET,
    )
    row = artifact_service.get_for_task(
        db,
        workspace_id=workspace_id,
        task_id=task_id,
        artifact_id=artifact_id,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found"
        )
    return ArtifactOut(
        id=row.id,
        task_id=row.task_id,
        workspace_id=row.workspace_id,
        type=row.type,
        status=row.status,
        content_ref=dict(row.content_ref or {}),
        title=row.title,
        skill_id=row.skill_id,
        created_at=row.created_at,
        payload=artifact_service.resolve_payload(task, row),
        lineage=artifact_service.lineage_for(task, row),
    )


@router.get("/{task_id}/steps", response_model=StepListOut)
def get_task_steps(
    workspace_id: UUID,
    task_id: UUID,
    ctx: tuple[User, WorkspaceMember] = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> StepListOut:
    user, member = ctx
    _require_task_access(
        db,
        workspace_id=workspace_id,
        task_id=task_id,
        member=member,
        user=user,
        action=perm.RUN_STEPS,
    )
    steps = task_service.list_steps(db, task_id=task_id)
    return StepListOut(items=[StepOut.model_validate(s) for s in steps])


@router.get("/{task_id}/events")
def stream_task_events(
    workspace_id: UUID,
    task_id: UUID,
    ctx: tuple[User, WorkspaceMember] = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """T-10: SSE progress stream for Analyze Runs (steps/status/terminal).

    Not LLM token streaming. Backed by polling Task + agent_run_steps.
    """
    user, member = ctx
    _require_task_access(
        db,
        workspace_id=workspace_id,
        task_id=task_id,
        member=member,
        user=user,
        action=perm.RUN_STEPS,
    )

    settings = get_settings()
    generator = task_events.iter_task_progress_events(
        workspace_id=workspace_id,
        task_id=task_id,
        poll_seconds=settings.task_sse_poll_seconds,
        heartbeat_seconds=settings.task_sse_heartbeat_seconds,
        max_seconds=settings.task_sse_max_seconds,
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{task_id}/cancel", response_model=TaskOut)
def cancel_task(
    workspace_id: UUID,
    task_id: UUID,
    ctx: tuple[User, WorkspaceMember] = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> TaskOut:
    user, member = ctx
    try:
        task = task_service.cancel_task(
            db,
            workspace_id=workspace_id,
            task_id=task_id,
            user_id=user.id,
            member_role=member.role,
            member=member,
        )
    except TaskServiceError as exc:
        raise _http_error(exc) from exc
    return TaskOut.model_validate(task)
