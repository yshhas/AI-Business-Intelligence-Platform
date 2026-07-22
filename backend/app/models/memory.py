"""Workspace column memory — Wave 3 MVP (linking synonyms, not chat)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base


class WorkspaceColumnMemory(Base):
    __tablename__ = "workspace_column_memory"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "dataset_id",
            "phrase",
            name="uq_ws_col_memory_ws_ds_phrase",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=True, index=True
    )
    phrase: Mapped[str] = mapped_column(String(200), nullable=False)
    column_tokens: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
