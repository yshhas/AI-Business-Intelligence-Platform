"""HITL H2 T1: hitl_resume_requested flag for Approve→enqueue (Worker CAS is T2).

Revision ID: 0016_hitl_h2_resume_requested
Revises: 0015_hitl_h1_awaiting_approval
Create Date: 2026-07-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016_hitl_h2_resume_requested"
down_revision: Union[str, Sequence[str], None] = "0015_hitl_h1_awaiting_approval"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "analysis_tasks",
        sa.Column(
            "hitl_resume_requested",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("analysis_tasks", "hitl_resume_requested")
