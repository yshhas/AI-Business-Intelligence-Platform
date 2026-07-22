import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base


class Dataset(Base):
    """Dataset binding: file→DuckDB (Phase 2) or postgres_ro (M3)."""

    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="file")
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    # Primary relation id: DuckDB ds_* or Postgres public.table (M3 keeps name frozen)
    duckdb_table: Mapped[str] = mapped_column(String(120), nullable=False)
    schema_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="processing")
    # M3: non-secret config e.g. {"connection_ref":"default","allowed_tables":[...]}
    source_config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    workspace: Mapped["Workspace"] = relationship(back_populates="datasets")
    creator: Mapped["User"] = relationship(back_populates="datasets")
    analysis_tasks: Mapped[list["AnalysisTask"]] = relationship(back_populates="dataset")
    acl_entries: Mapped[list["DatasetAcl"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )


class DatasetAcl(Base):
    """P1: per-user Dataset grants within a workspace (Shell only; not IAM)."""

    __tablename__ = "dataset_acl"
    __table_args__ = (
        UniqueConstraint("dataset_id", "user_id", name="uq_dataset_acl_dataset_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    can_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Wave 3: optional table subset projected into SQL Gate allowlist (null = full dataset allowlist)
    tables_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    dataset: Mapped["Dataset"] = relationship(back_populates="acl_entries")
