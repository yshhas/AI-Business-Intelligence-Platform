"""M5 thin Resource Permission + P1 Dataset ACL — Product Shell only (not IAM).

Workspace roles: owner | analyst | viewer.
Kernel / Skill / Policy / Worker do not import this module for execution logic.
ACL answers “may this user touch the Dataset/Run?”; Policy Gate answers “may this SQL run?”.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AnalysisTask, Dataset, DatasetAcl, Workspace, WorkspaceMember

ROLE_OWNER = "owner"
ROLE_ANALYST = "analyst"
ROLE_VIEWER = "viewer"
MUTATOR_ROLES = frozenset({ROLE_OWNER, ROLE_ANALYST})

# Actions (stable vocabulary for Demo / docs)
DATASET_LIST = "dataset.list"
DATASET_GET = "dataset.get"
DATASET_PREVIEW = "dataset.preview"
DATASET_CREATE_FILE = "dataset.create_file"
DATASET_BIND_POSTGRES_RO = "dataset.bind_postgres_ro"
DATASET_ACL_GET = "dataset.acl.get"
DATASET_ACL_PUT = "dataset.acl.put"
RUN_CREATE = "run.create"
RUN_GET = "run.get"
RUN_LIST = "run.list"
RUN_EXECUTION = "run.execution"
RUN_STEPS = "run.steps"
RUN_CANCEL = "run.cancel"
ARTIFACT_LIST = "artifact.list"
ARTIFACT_GET = "artifact.get"
SKILL_INVOKE = "skill.invoke"
WORKSPACE_UPDATE = "workspace.update"

ACL_MODE_DEFAULT_OPEN = "default_open"
ACL_MODE_RESTRICTED = "acl_restricted"


class PermissionError(Exception):
    """In-workspace role/ACL insufficient → map to HTTP 403."""

    def __init__(self, message: str, *, status_code: int = 403) -> None:
        super().__init__(message)
        self.status_code = status_code


def normalize_role(role: str | None) -> str:
    r = (role or "").strip().lower()
    if r in {ROLE_OWNER, ROLE_ANALYST, ROLE_VIEWER}:
        return r
    return ROLE_VIEWER


def is_mutator(role: str | None) -> bool:
    return normalize_role(role) in MUTATOR_ROLES


def is_workspace_owner(
    member: WorkspaceMember,
    *,
    workspace: Workspace | None = None,
) -> bool:
    if normalize_role(member.role) == ROLE_OWNER:
        return True
    if workspace is not None and workspace.owner_user_id == member.user_id:
        return True
    return False


def dataset_acl_row_count(db: Session, dataset_id: UUID) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(DatasetAcl).where(
                DatasetAcl.dataset_id == dataset_id
            )
        )
        or 0
    )


def get_acl_entry(
    db: Session, *, dataset_id: UUID, user_id: UUID
) -> DatasetAcl | None:
    return db.execute(
        select(DatasetAcl).where(
            DatasetAcl.dataset_id == dataset_id,
            DatasetAcl.user_id == user_id,
        )
    ).scalar_one_or_none()


def acl_mode_for_dataset(db: Session, dataset_id: UUID) -> str:
    return (
        ACL_MODE_RESTRICTED
        if dataset_acl_row_count(db, dataset_id) > 0
        else ACL_MODE_DEFAULT_OPEN
    )


def can_read_dataset(
    db: Session,
    member: WorkspaceMember,
    dataset: Dataset,
    *,
    workspace: Workspace | None = None,
) -> bool:
    if is_workspace_owner(member, workspace=workspace):
        return True
    if dataset_acl_row_count(db, dataset.id) == 0:
        return True  # M5 compat: any member may read
    entry = get_acl_entry(db, dataset_id=dataset.id, user_id=member.user_id)
    return bool(entry and entry.can_read)


def can_run_dataset(
    db: Session,
    member: WorkspaceMember,
    dataset: Dataset,
    *,
    workspace: Workspace | None = None,
) -> bool:
    if is_workspace_owner(member, workspace=workspace):
        return True
    role = normalize_role(member.role)
    if role not in MUTATOR_ROLES:
        return False
    if dataset_acl_row_count(db, dataset.id) == 0:
        return True  # M5 compat: analysts may Analyze
    entry = get_acl_entry(db, dataset_id=dataset.id, user_id=member.user_id)
    return bool(entry and entry.can_run)


def can_access_task(
    db: Session,
    member: WorkspaceMember,
    task: AnalysisTask,
    dataset: Dataset,
    *,
    workspace: Workspace | None = None,
    user_id=None,
) -> bool:
    """Read Run/Trace/Artifact: creator, workspace owner, or dataset read grant."""
    uid = user_id if user_id is not None else member.user_id
    if is_workspace_owner(member, workspace=workspace):
        return True
    if task.user_id == uid:
        return True
    return can_read_dataset(db, member, dataset, workspace=workspace)


def can(
    member: WorkspaceMember,
    action: str,
    *,
    dataset: Dataset | None = None,
    task: AnalysisTask | None = None,
    workspace: Workspace | None = None,
    user_id=None,
    skill_id: str | None = None,
    db: Session | None = None,
) -> bool:
    """Return True if workspace member may perform action."""
    role = normalize_role(member.role)

    if action in {DATASET_ACL_GET, DATASET_ACL_PUT}:
        return is_workspace_owner(member, workspace=workspace)

    if action == DATASET_LIST:
        return True  # filtering happens in list_datasets

    if action in {DATASET_GET, DATASET_PREVIEW}:
        if dataset is None:
            return False
        if db is None:
            # Role-only fallback (legacy callers / unit without Session)
            return True
        return can_read_dataset(db, member, dataset, workspace=workspace)

    if action in {
        DATASET_CREATE_FILE,
        DATASET_BIND_POSTGRES_RO,
        WORKSPACE_UPDATE,
    }:
        return role in MUTATOR_ROLES

    if action == RUN_CREATE:
        if role not in MUTATOR_ROLES:
            return False
        if dataset is None:
            return False
        if dataset.source_type not in {"file", "postgres_ro", "mysql_ro"}:
            return False
        if db is None:
            return True
        return can_run_dataset(db, member, dataset, workspace=workspace)

    if action == SKILL_INVOKE:
        if skill_id:
            try:
                from app.core.repo_path import ensure_repo_root_on_path

                ensure_repo_root_on_path()
                from agent.kernel import registry

                registry.ensure_platform_registrations()
                if registry.get_skill_meta(skill_id) is None:
                    return False
            except Exception:  # noqa: BLE001
                return False
        return can(
            member,
            RUN_CREATE,
            dataset=dataset,
            task=task,
            workspace=workspace,
            user_id=user_id,
            db=db,
        )

    if action in {
        RUN_LIST,
        RUN_GET,
        RUN_EXECUTION,
        RUN_STEPS,
        ARTIFACT_LIST,
        ARTIFACT_GET,
    }:
        if task is None:
            # list: route filters; bare allow membership
            return True
        if dataset is None:
            return False
        if db is None:
            return True
        return can_access_task(
            db, member, task, dataset, workspace=workspace, user_id=user_id
        )

    if action == RUN_CANCEL:
        if task is None or user_id is None:
            return False
        is_creator = task.user_id == user_id
        is_owner = is_workspace_owner(member, workspace=workspace) or (
            workspace is not None and workspace.owner_user_id == user_id
        )
        return bool(is_creator or is_owner)

    return False


def require(
    member: WorkspaceMember,
    action: str,
    *,
    dataset: Dataset | None = None,
    task: AnalysisTask | None = None,
    workspace: Workspace | None = None,
    user_id=None,
    skill_id: str | None = None,
    db: Session | None = None,
) -> None:
    if not can(
        member,
        action,
        dataset=dataset,
        task=task,
        workspace=workspace,
        user_id=user_id,
        skill_id=skill_id,
        db=db,
    ):
        raise PermissionError(_deny_message(action), status_code=403)


def build_authorization_snapshot(
    *,
    actor_user_id: UUID,
    actor_role: str,
    dataset: Dataset,
    authorized_tables: list[str],
    acl_mode: str,
) -> dict:
    """Audit-only Trace field — not a permission cache."""
    return {
        "actor_user_id": str(actor_user_id),
        "actor_role": normalize_role(actor_role),
        "dataset_id": str(dataset.id),
        "authorized_tables": list(authorized_tables),
        "acl_mode": acl_mode,
    }


def _deny_message(action: str) -> str:
    messages = {
        DATASET_CREATE_FILE: "Insufficient role: viewer cannot upload datasets",
        DATASET_BIND_POSTGRES_RO: (
            "Insufficient role: only owner or analyst can bind a postgres_ro data source"
        ),
        DATASET_GET: "Insufficient permission: cannot access this dataset",
        DATASET_PREVIEW: "Insufficient permission: cannot preview this dataset",
        DATASET_ACL_GET: "Only workspace owner can view dataset ACL",
        DATASET_ACL_PUT: "Only workspace owner can update dataset ACL",
        RUN_CREATE: "Insufficient permission: cannot create analysis runs on this dataset",
        RUN_GET: "Insufficient permission: cannot access this run",
        RUN_EXECUTION: "Insufficient permission: cannot access this run trace",
        RUN_STEPS: "Insufficient permission: cannot access this run steps",
        ARTIFACT_LIST: "Insufficient permission: cannot access artifacts for this run",
        ARTIFACT_GET: "Insufficient permission: cannot access this artifact",
        RUN_CANCEL: "Only the task creator or workspace owner can cancel this run",
        WORKSPACE_UPDATE: "Insufficient role: viewer cannot update workspace",
        SKILL_INVOKE: "Insufficient permission: cannot invoke skill on this dataset",
    }
    return messages.get(action, f"Insufficient role for action {action}")
