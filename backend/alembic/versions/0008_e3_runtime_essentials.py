"""E3 Runtime Essentials: last_heartbeat_at on analysis_tasks.

Revision ID: 0008_e3_runtime_essentials
Revises: 0007_m6_run_artifacts
Create Date: 2026-07-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_e3_runtime_essentials"
down_revision: Union[str, Sequence[str], None] = "0007_m6_run_artifacts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "analysis_tasks",
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("analysis_tasks", "last_heartbeat_at")
