"""M6: run_artifacts thin metadata table.

Revision ID: 0007_m6_run_artifacts
Revises: 0006_m4_execution_trace
Create Date: 2026-07-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_m6_run_artifacts"
down_revision: Union[str, Sequence[str], None] = "0006_m4_execution_trace"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "run_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("content_ref", sa.JSON(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=True),
        sa.Column("skill_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["analysis_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_run_artifacts_task_id", "run_artifacts", ["task_id"])
    op.create_index("ix_run_artifacts_workspace_id", "run_artifacts", ["workspace_id"])
    op.create_index("ix_run_artifacts_type", "run_artifacts", ["type"])


def downgrade() -> None:
    op.drop_index("ix_run_artifacts_type", table_name="run_artifacts")
    op.drop_index("ix_run_artifacts_workspace_id", table_name="run_artifacts")
    op.drop_index("ix_run_artifacts_task_id", table_name="run_artifacts")
    op.drop_table("run_artifacts")
