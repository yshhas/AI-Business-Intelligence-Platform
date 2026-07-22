"""P0-2 Soft Cost Budget: llm_total_tokens on analysis_tasks.

Revision ID: 0010_p0_2_cost_budget
Revises: 0009_skill_lifecycle_lite
Create Date: 2026-07-22

Denormalized Run-level token sum for soft workspace/day budget checks.
Detail truth remains agent_run_steps.output_json.llm.usage.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_p0_2_cost_budget"
down_revision: Union[str, Sequence[str], None] = "0009_skill_lifecycle_lite"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "analysis_tasks",
        sa.Column("llm_total_tokens", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("analysis_tasks", "llm_total_tokens")
