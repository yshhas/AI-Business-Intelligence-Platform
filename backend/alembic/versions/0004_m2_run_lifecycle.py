"""M2 Run lifecycle columns on analysis_tasks."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_m2_run_lifecycle"
down_revision = "0003_phase3_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_tasks",
        sa.Column(
            "cancel_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "analysis_tasks",
        sa.Column("failure_class", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "analysis_tasks",
        sa.Column("timeout_seconds", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("analysis_tasks", "timeout_seconds")
    op.drop_column("analysis_tasks", "failure_class")
    op.drop_column("analysis_tasks", "cancel_requested")
