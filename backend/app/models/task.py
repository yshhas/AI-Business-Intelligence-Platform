import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base


class AnalysisTask(Base):
    """Async analysis job (Phase 3 skeleton — mock worker fills result_json)."""

    __tablename__ = "analysis_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # M2 Run lifecycle
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    failure_class: Mapped[str | None] = mapped_column(String(40), nullable=True)
    timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # M4 Trace filter columns (denormalized from platform.execution / data_plane)
    skill_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_type: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    policy_denied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # T-09 Skill Lifecycle lite
    skill_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # P0-2 Soft Cost Budget — denormalized sum from step usage (detail truth = steps)
    llm_total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # E3: optional freshness for stale-running reclaim (not a lease)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    workspace: Mapped["Workspace"] = relationship(back_populates="analysis_tasks")
    dataset: Mapped["Dataset"] = relationship(back_populates="analysis_tasks")
    user: Mapped["User"] = relationship(back_populates="analysis_tasks")
    steps: Mapped[list["AgentRunStep"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="AgentRunStep.step_no"
    )
    artifacts: Mapped[list["RunArtifact"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="RunArtifact.created_at"
    )


class AgentRunStep(Base):
    """Per-task execution timeline (Phase 3 mock steps; later LangGraph nodes)."""

    __tablename__ = "agent_run_steps"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_no: Mapped[int] = mapped_column(Integer, nullable=False)
    node_name: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")
    input_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    task: Mapped["AnalysisTask"] = relationship(back_populates="steps")
