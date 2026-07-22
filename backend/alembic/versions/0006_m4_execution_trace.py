"""M4: denormalized Trace filter columns on analysis_tasks.

Revision ID: 0006_m4_execution_trace
Revises: 0005_m3_postgres_ro
Create Date: 2026-07-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_m4_execution_trace"
down_revision: Union[str, Sequence[str], None] = "0005_m3_postgres_ro"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "analysis_tasks",
        sa.Column("skill_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "analysis_tasks",
        sa.Column("source_type", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "analysis_tasks",
        sa.Column(
            "policy_denied",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index("ix_analysis_tasks_skill_id", "analysis_tasks", ["skill_id"])
    op.create_index("ix_analysis_tasks_source_type", "analysis_tasks", ["source_type"])
    op.create_index("ix_analysis_tasks_policy_denied", "analysis_tasks", ["policy_denied"])


def downgrade() -> None:
    op.drop_index("ix_analysis_tasks_policy_denied", table_name="analysis_tasks")
    op.drop_index("ix_analysis_tasks_source_type", table_name="analysis_tasks")
    op.drop_index("ix_analysis_tasks_skill_id", table_name="analysis_tasks")
    op.drop_column("analysis_tasks", "policy_denied")
    op.drop_column("analysis_tasks", "source_type")
    op.drop_column("analysis_tasks", "skill_id")
