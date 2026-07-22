"""Analysis task orchestration — create/enqueue/query/cancel (M2 Run lifecycle)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.observability import log_run
from app.models import AgentRunStep, AnalysisTask, Dataset, DatasetAcl, Workspace
from app.services import cost_budget
from app.services import queue as task_queue
from app.services import permissions as perm
from app.services import run_lifecycle as rl
from app.services import runtime_essentials as rt
from app.services import skill_lifecycle as skills
from app.services.cost_budget import BudgetError
from app.services.permissions import PermissionError
from app.services.runtime_essentials import CapacityError
from app.services.skill_lifecycle import SkillLifecycleError

logger = logging.getLogger(__name__)


def _metric_enqueue(result: str) -> None:
    try:
        from app.core.metrics import observe_enqueue

        observe_enqueue(result)
    except Exception:  # noqa: BLE001
        pass


def _metric_terminal(*, status: str, failure_class: str | None = None) -> None:
    try:
        from app.core.metrics import observe_task_terminal

        observe_task_terminal(status=status, failure_class=failure_class)
    except Exception:  # noqa: BLE001
        pass


class TaskServiceError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def create_task(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    dataset_id: UUID,
    question: str,
    member_role: str | None = None,
    member: object | None = None,
    skill_id: str | None = None,
    idempotency_key: str | None = None,
) -> AnalysisTask:
    from app.services import idempotency as idem

    claimed_pending = False
    if idempotency_key:
        try:
            existing_id = idem.claim_idempotency_key(
                workspace_id=workspace_id, user_id=user_id, idem_key=idempotency_key
            )
        except idem.IdempotencyError as exc:
            raise TaskServiceError(str(exc), status_code=exc.status_code) from exc
        if existing_id is not None:
            existing = db.get(AnalysisTask, existing_id)
            if existing is not None and existing.workspace_id == workspace_id:
                return existing
        else:
            claimed_pending = True

    def _abort_idem(exc: TaskServiceError) -> TaskServiceError:
        if claimed_pending and idempotency_key:
            idem.release_claim(
                workspace_id=workspace_id, user_id=user_id, idem_key=idempotency_key
            )
        return exc

    dataset = db.execute(
        select(Dataset).where(
            Dataset.id == dataset_id,
            Dataset.workspace_id == workspace_id,
        )
    ).scalar_one_or_none()
    if dataset is None:
        raise _abort_idem(TaskServiceError("Dataset not found", status_code=404))
    if dataset.status != "ready":
        raise _abort_idem(
            TaskServiceError(
                f"Dataset is not ready (status={dataset.status})",
                status_code=409,
            )
        )

    requested_skill = (skill_id or "data.bi").strip() or "data.bi"

    # M5 + P1: unified resource permission (viewer cannot create Run; ACL can_run)
    workspace = db.get(Workspace, workspace_id)
    if member is not None:
        try:
            perm.require(
                member,  # type: ignore[arg-type]
                perm.RUN_CREATE,
                dataset=dataset,
                workspace=workspace,
                db=db,
            )
            perm.require(
                member,  # type: ignore[arg-type]
                perm.SKILL_INVOKE,
                dataset=dataset,
                workspace=workspace,
                user_id=user_id,
                skill_id=requested_skill,
                db=db,
            )
        except PermissionError as exc:
            raise _abort_idem(
                TaskServiceError(str(exc), status_code=exc.status_code)
            ) from exc
    elif member_role is not None:
        # Backward-compatible path for scripts without full member object
        fake = type("M", (), {"role": member_role, "user_id": user_id})()
        try:
            perm.require(
                fake,  # type: ignore[arg-type]
                perm.RUN_CREATE,
                dataset=dataset,
                workspace=workspace,
                db=db,
            )
        except PermissionError as exc:
            raise _abort_idem(
                TaskServiceError(str(exc), status_code=exc.status_code)
            ) from exc

    q = question.strip()
    if not q:
        raise _abort_idem(TaskServiceError("Question must not be empty", status_code=400))

    settings = get_settings()
    try:
        skill_id, skill_version = skills.assert_skill_invokable(
            settings, skill_id=requested_skill
        )
    except SkillLifecycleError as exc:
        raise _abort_idem(
            TaskServiceError(str(exc), status_code=exc.status_code)
        ) from exc

    try:
        rt.assert_enqueue_allowed(db, settings)
    except CapacityError as exc:
        _metric_enqueue("capacity_rejected")
        raise _abort_idem(TaskServiceError(str(exc), status_code=429)) from exc

    # P0-2 Soft Cost Budget — before enqueue; audit row + 429 (no Redis push)
    try:
        cost_budget.assert_budget_allowed(db, workspace_id=workspace_id, settings=settings)
    except BudgetError as exc:
        now = datetime.now(UTC)
        rejected = AnalysisTask(
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            user_id=user_id,
            question=q,
            status="failed",
            cancel_requested=False,
            failure_class=rl.FAILURE_BUDGET,
            error_message=str(exc),
            timeout_seconds=settings.run_timeout_seconds,
            skill_id=skill_id,
            skill_version=skill_version,
            finished_at=now,
            llm_total_tokens=None,
        )
        db.add(rejected)
        db.flush()
        rejected.result_json = rl.attach_run_platform(
            {
                "summary": "",
                "sql": None,
                "table_preview": {"columns": [], "rows": []},
                "charts": [],
                "report": None,
                "limitations": [
                    "Soft token budget rejected enqueue; in-flight Runs were not cancelled."
                ],
            },
            status="failed",
            failure_class=rl.FAILURE_BUDGET,
            cancel_requested=False,
            timeout_seconds=settings.run_timeout_seconds,
            task_id=str(rejected.id),
        )
        db.add(rejected)
        db.commit()
        db.refresh(rejected)
        _metric_enqueue("budget_rejected")
        _metric_terminal(status="failed", failure_class=rl.FAILURE_BUDGET)
        log_run(
            logger,
            logging.WARNING,
            str(exc),
            run_id=rejected.id,
            status="failed",
            failure_class=rl.FAILURE_BUDGET,
            skill_id=skill_id,
        )
        if idempotency_key:
            try:
                idem.remember_task_id(
                    workspace_id=workspace_id,
                    user_id=user_id,
                    idem_key=idempotency_key,
                    task_id=rejected.id,
                )
            except idem.IdempotencyError:
                pass
        raise TaskServiceError(str(exc), status_code=429) from exc

    task = AnalysisTask(
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        user_id=user_id,
        question=q,
        status="pending",
        cancel_requested=False,
        failure_class=None,
        timeout_seconds=settings.run_timeout_seconds,
        skill_id=skill_id,
        skill_version=skill_version,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    try:
        # Re-check depth after commit (best-effort race window)
        rt.assert_enqueue_allowed(db, settings)
        task_queue.enqueue_task(task.id)
        _metric_enqueue("ok")
    except CapacityError as exc:
        task.status = "failed"
        task.failure_class = rl.FAILURE_CAPACITY
        task.error_message = str(exc)
        task.finished_at = datetime.now(UTC)
        db.add(task)
        db.commit()
        db.refresh(task)
        _metric_enqueue("capacity_rejected")
        _metric_terminal(status="failed", failure_class=rl.FAILURE_CAPACITY)
        log_run(
            logger,
            logging.WARNING,
            str(exc),
            run_id=task.id,
            status="failed",
            failure_class=rl.FAILURE_CAPACITY,
        )
        raise TaskServiceError(str(exc), status_code=429) from exc
    except Exception as exc:  # noqa: BLE001
        task.status = "failed"
        task.failure_class = rl.FAILURE_ENQUEUE
        task.error_message = f"Failed to enqueue task: {exc}"
        task.finished_at = datetime.now(UTC)
        db.add(task)
        db.commit()
        db.refresh(task)
        _metric_enqueue("enqueue_error")
        _metric_terminal(status="failed", failure_class=rl.FAILURE_ENQUEUE)
        log_run(
            logger,
            logging.ERROR,
            task.error_message,
            run_id=task.id,
            status="failed",
            failure_class=rl.FAILURE_ENQUEUE,
        )
        raise TaskServiceError(task.error_message, status_code=503) from exc

    log_run(
        logger,
        logging.INFO,
        "enqueued",
        run_id=task.id,
        status="pending",
        skill_id=skill_id,
    )
    if idempotency_key:
        try:
            idem.remember_task_id(
                workspace_id=workspace_id,
                user_id=user_id,
                idem_key=idempotency_key,
                task_id=task.id,
            )
        except idem.IdempotencyError as exc:
            raise TaskServiceError(str(exc), status_code=exc.status_code) from exc
    return task


def list_tasks(
    db: Session,
    *,
    workspace_id: UUID,
    limit: int = 50,
    status: str | None = None,
    skill_id: str | None = None,
    source_type: str | None = None,
    policy_denied: bool | None = None,
    failure_class: str | None = None,
    member=None,
    user_id: UUID | None = None,
) -> list[AnalysisTask]:
    limit = max(1, min(limit, 100))
    stmt = select(AnalysisTask).where(AnalysisTask.workspace_id == workspace_id)
    if status:
        stmt = stmt.where(AnalysisTask.status == status)
    if skill_id:
        stmt = stmt.where(AnalysisTask.skill_id == skill_id)
    if source_type:
        stmt = stmt.where(AnalysisTask.source_type == source_type)
    if policy_denied is not None:
        stmt = stmt.where(AnalysisTask.policy_denied.is_(policy_denied))
    if failure_class:
        stmt = stmt.where(AnalysisTask.failure_class == failure_class)
    stmt = stmt.order_by(AnalysisTask.created_at.desc()).limit(limit)
    items = list(db.scalars(stmt).all())
    if member is None:
        return items
    workspace = db.get(Workspace, workspace_id)
    if not items:
        return []

    uid = user_id if user_id is not None else getattr(member, "user_id", None)
    dataset_ids = {t.dataset_id for t in items}
    datasets = {
        d.id: d
        for d in db.scalars(select(Dataset).where(Dataset.id.in_(dataset_ids))).all()
    }

    # Batch ACL preload (P1.5) — avoid per-task COUNT/GET round-trips.
    owner = perm.is_workspace_owner(member, workspace=workspace)
    datasets_with_acl: set[UUID] = set()
    acl_by_dataset: dict[UUID, DatasetAcl] = {}
    if not owner and dataset_ids:
        restricted = db.execute(
            select(DatasetAcl.dataset_id, func.count())
            .where(DatasetAcl.dataset_id.in_(dataset_ids))
            .group_by(DatasetAcl.dataset_id)
        ).all()
        datasets_with_acl = {row[0] for row in restricted if int(row[1] or 0) > 0}
        if uid is not None and datasets_with_acl:
            entries = db.scalars(
                select(DatasetAcl).where(
                    DatasetAcl.user_id == uid,
                    DatasetAcl.dataset_id.in_(datasets_with_acl),
                )
            ).all()
            acl_by_dataset = {e.dataset_id: e for e in entries}

    visible: list[AnalysisTask] = []
    for task in items:
        dataset = datasets.get(task.dataset_id)
        if dataset is None:
            continue
        if owner or task.user_id == uid:
            visible.append(task)
            continue
        # Mirror can_read_dataset with preloaded ACL (default-open when no ACL rows).
        if task.dataset_id not in datasets_with_acl:
            visible.append(task)
            continue
        entry = acl_by_dataset.get(task.dataset_id)
        if entry is not None and entry.can_read:
            visible.append(task)
    return visible


def get_execution_trace(
    db: Session, *, workspace_id: UUID, task_id: UUID
) -> dict | None:
    """Return ExecutionTrace view for a Run (M4) — not an Audit product payload."""
    task = get_task(db, workspace_id=workspace_id, task_id=task_id)
    if task is None:
        return None
    platform = dict((task.result_json or {}).get("platform") or {})
    return {
        "run_id": str(task.id),
        "workspace_id": str(task.workspace_id),
        "dataset_id": str(task.dataset_id),
        "question": task.question,
        "status": task.status,
        "failure_class": task.failure_class,
        "skill_id": task.skill_id or platform.get("skill_id"),
        "skill_version": task.skill_version or platform.get("skill_version"),
        "source_type": task.source_type
        or (platform.get("data_plane") or {}).get("source_type"),
        "policy_denied": bool(task.policy_denied),
        "run": platform.get("run"),
        "data_plane": platform.get("data_plane"),
        "authorization": platform.get("authorization"),
        "sql_quality": platform.get("sql_quality"),
        "execution": platform.get("execution")
        or {
            "schema_version": 1,
            "tool_calls": [],
            "policy_decisions": [],
            "artifacts": [],
            "summary": {
                "tool_count": 0,
                "policy_decision_count": 0,
                "policy_deny_count": 0,
                "artifact_count": 0,
                "artifact_types": [],
                "incomplete": task.status
                in {"pending", "running", "cancelled", "timed_out"},
            },
        },
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
    }


def get_task(db: Session, *, workspace_id: UUID, task_id: UUID) -> AnalysisTask | None:
    return db.execute(
        select(AnalysisTask).where(
            AnalysisTask.id == task_id,
            AnalysisTask.workspace_id == workspace_id,
        )
    ).scalar_one_or_none()


def list_steps(db: Session, *, task_id: UUID) -> list[AgentRunStep]:
    stmt = (
        select(AgentRunStep)
        .where(AgentRunStep.task_id == task_id)
        .order_by(AgentRunStep.step_no.asc())
    )
    return list(db.scalars(stmt).all())


def cancel_task(
    db: Session,
    *,
    workspace_id: UUID,
    task_id: UUID,
    user_id: UUID,
    member_role: str,
    member: object | None = None,
) -> AnalysisTask:
    """Cancel a Run. Allowed: task creator or workspace owner."""
    task = get_task(db, workspace_id=workspace_id, task_id=task_id)
    if task is None:
        raise TaskServiceError("Task not found", status_code=404)

    workspace = db.get(Workspace, workspace_id)
    actor = member
    if actor is None:
        actor = type("M", (), {"role": member_role})()
    try:
        perm.require(
            actor,  # type: ignore[arg-type]
            perm.RUN_CANCEL,
            task=task,
            workspace=workspace,
            user_id=user_id,
        )
    except PermissionError as exc:
        raise TaskServiceError(str(exc), status_code=exc.status_code) from exc

    if task.status in rl.TERMINAL_STATUSES:
        raise TaskServiceError(
            f"Cannot cancel terminal run (status={task.status})",
            status_code=409,
        )

    now = datetime.now(UTC)
    if task.status == "pending":
        task.cancel_requested = True
        task.status = "cancelled"
        task.failure_class = rl.FAILURE_CANCELLED
        task.error_message = "Run cancelled before start"
        task.finished_at = now
        task.result_json = rl.attach_run_platform(
            {
                "summary": "",
                "sql": None,
                "table_preview": {"columns": [], "rows": []},
                "charts": [],
                "report": None,
                "limitations": list(rl.CANCEL_LIMITATIONS),
                "mock": False,
            },
            status="cancelled",
            failure_class=rl.FAILURE_CANCELLED,
            cancel_requested=True,
            timeout_seconds=task.timeout_seconds,
            task_id=str(task.id),
        )
    else:
        # running — cooperative cancel
        task.cancel_requested = True
        db.add(task)
        db.commit()
        db.refresh(task)
        log_run(
            logger,
            logging.INFO,
            "cancel_requested while running",
            run_id=task.id,
            status=task.status,
            failure_class=task.failure_class,
        )
        return task

    db.add(task)
    db.commit()
    db.refresh(task)
    log_run(
        logger,
        logging.INFO,
        "cancelled before start",
        run_id=task.id,
        status=task.status,
        failure_class=task.failure_class,
    )
    return task
