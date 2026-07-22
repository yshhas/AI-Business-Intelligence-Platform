"""P1 Dataset ACL — thin resource grants (Shell only).

Revision ID: 0011_p1_dataset_acl
Revises: 0010_p0_2_cost_budget
Create Date: 2026-07-22

Empty ACL for a dataset ⇒ M5 role-only behavior (compat).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_p1_dataset_acl"
down_revision: Union[str, Sequence[str], None] = "0010_p0_2_cost_budget"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dataset_acl",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("can_read", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("can_run", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "user_id", name="uq_dataset_acl_dataset_user"),
    )
    op.create_index("ix_dataset_acl_workspace_id", "dataset_acl", ["workspace_id"])
    op.create_index("ix_dataset_acl_dataset_id", "dataset_acl", ["dataset_id"])
    op.create_index("ix_dataset_acl_user_id", "dataset_acl", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_dataset_acl_user_id", table_name="dataset_acl")
    op.drop_index("ix_dataset_acl_dataset_id", table_name="dataset_acl")
    op.drop_index("ix_dataset_acl_workspace_id", table_name="dataset_acl")
    op.drop_table("dataset_acl")
