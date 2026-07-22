"""HITL H1: require_sql_approval + approval_requested_at.

Revision ID: 0015_hitl_h1_awaiting_approval
Revises: 0014_sprint2_refresh_memory
Create Date: 2026-07-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015_hitl_h1_awaiting_approval"
down_revision: Union[str, Sequence[str], None] = "0014_sprint2_refresh_memory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "analysis_tasks",
        sa.Column(
            "require_sql_approval",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "analysis_tasks",
        sa.Column("approval_requested_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("analysis_tasks", "approval_requested_at")
    op.drop_column("analysis_tasks", "require_sql_approval")
