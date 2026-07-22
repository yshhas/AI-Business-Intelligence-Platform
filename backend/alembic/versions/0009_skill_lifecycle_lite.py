"""T-09 Skill Lifecycle lite: skill_version on analysis_tasks.

Revision ID: 0009_skill_lifecycle_lite
Revises: 0008_e3_runtime_essentials
Create Date: 2026-07-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_skill_lifecycle_lite"
down_revision: Union[str, Sequence[str], None] = "0008_e3_runtime_essentials"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "analysis_tasks",
        sa.Column("skill_version", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("analysis_tasks", "skill_version")
