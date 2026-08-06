from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class TaskCreateRequest(BaseModel):
    dataset_id: UUID
    question: str = Field(min_length=1, max_length=4000)
    skill_id: str | None = Field(default=None, max_length=64)
    require_sql_approval: bool = False


class TaskRejectRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class TaskOut(BaseModel):
    id: UUID
    workspace_id: UUID
    dataset_id: UUID
    user_id: UUID
    question: str
    status: str
    result_json: dict[str, Any] | None = None
    error_message: str | None = None
    cancel_requested: bool = False
    failure_class: str | None = None
    timeout_seconds: int | None = None
    skill_id: str | None = None
    skill_version: str | None = None
    source_type: str | None = None
    policy_denied: bool = False
    llm_total_tokens: int | None = None
    require_sql_approval: bool = False
    approval_requested_at: datetime | None = None
    hitl_resume_requested: bool = False
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}


class TaskListOut(BaseModel):
    items: list[TaskOut]


class StepOut(BaseModel):
    id: UUID
    task_id: UUID
    step_no: int
    node_name: str
    status: str
    input_json: dict[str, Any] | None = None
    output_json: dict[str, Any] | None = None
    error_message: str | None = None
    latency_ms: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class StepListOut(BaseModel):
    items: list[StepOut]


class ExecutionTraceOut(BaseModel):
    """M4 Execution Trace — Run-centric, not an Audit product document."""

    run_id: str
    workspace_id: str
    dataset_id: str
    question: str
    status: str
    failure_class: str | None = None
    skill_id: str | None = None
    skill_version: str | None = None
    source_type: str | None = None
    policy_denied: bool = False
    run: dict[str, Any] | None = None
    data_plane: dict[str, Any] | None = None
    authorization: dict[str, Any] | None = None
    sql_quality: dict[str, Any] | None = None
    execution: dict[str, Any]
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class ArtifactOut(BaseModel):
    """M6 Artifact metadata (+ optional resolved payload / lineage)."""

    id: UUID
    task_id: UUID
    workspace_id: UUID
    type: str
    status: str
    content_ref: dict[str, Any]
    title: str | None = None
    skill_id: str | None = None
    created_at: datetime
    payload: Any | None = None
    lineage: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class ArtifactListOut(BaseModel):
    items: list[ArtifactOut]
