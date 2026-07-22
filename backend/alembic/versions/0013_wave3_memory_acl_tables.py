"""Wave 3: workspace memory + ACL table projection columns.

Revision ID: 0013_wave3_memory_acl_tables
Revises: 0012_task_list_index
Create Date: 2026-07-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013_wave3_memory_acl_tables"
down_revision: Union[str, Sequence[str], None] = "0012_task_list_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dataset_acl",
        sa.Column("tables_json", sa.JSON(), nullable=True),
    )
    op.create_table(
        "workspace_column_memory",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=True),
        sa.Column("phrase", sa.String(length=200), nullable=False),
        sa.Column("column_tokens", sa.JSON(), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "dataset_id",
            "phrase",
            name="uq_ws_col_memory_ws_ds_phrase",
        ),
    )
    op.create_index(
        "ix_workspace_column_memory_workspace_id",
        "workspace_column_memory",
        ["workspace_id"],
    )
    op.create_index(
        "ix_workspace_column_memory_dataset_id",
        "workspace_column_memory",
        ["dataset_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_workspace_column_memory_dataset_id", table_name="workspace_column_memory")
    op.drop_index("ix_workspace_column_memory_workspace_id", table_name="workspace_column_memory")
    op.drop_table("workspace_column_memory")
    op.drop_column("dataset_acl", "tables_json")
