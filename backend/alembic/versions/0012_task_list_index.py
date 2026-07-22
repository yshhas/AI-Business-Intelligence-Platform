"""Composite index for workspace task list filters (status + recency).

Revision ID: 0012_task_list_index
Revises: 0011_p1_dataset_acl
Create Date: 2026-07-22
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0012_task_list_index"
down_revision: Union[str, Sequence[str], None] = "0011_p1_dataset_acl"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_analysis_tasks_ws_status_created",
        "analysis_tasks",
        ["workspace_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_tasks_ws_status_created", table_name="analysis_tasks")
