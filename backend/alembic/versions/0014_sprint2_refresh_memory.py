"""Sprint 2: refresh_sessions + memory expires_at.

Revision ID: 0014_sprint2_refresh_memory
Revises: 0013_wave3_memory_acl_tables
Create Date: 2026-07-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_sprint2_refresh_memory"
down_revision: Union[str, Sequence[str], None] = "0013_wave3_memory_acl_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "refresh_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("jti", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_jti", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("jti", name="uq_refresh_sessions_jti"),
    )
    op.create_index("ix_refresh_sessions_jti", "refresh_sessions", ["jti"])
    op.create_index("ix_refresh_sessions_user_id", "refresh_sessions", ["user_id"])
    op.create_index(
        "ix_refresh_sessions_user_revoked",
        "refresh_sessions",
        ["user_id", "revoked_at"],
    )
    op.create_index("ix_refresh_sessions_expires_at", "refresh_sessions", ["expires_at"])

    op.add_column(
        "workspace_column_memory",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_workspace_column_memory_ws_expires",
        "workspace_column_memory",
        ["workspace_id", "expires_at"],
    )
    op.create_index(
        "ix_workspace_column_memory_ws_updated",
        "workspace_column_memory",
        ["workspace_id", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workspace_column_memory_ws_updated",
        table_name="workspace_column_memory",
    )
    op.drop_index(
        "ix_workspace_column_memory_ws_expires",
        table_name="workspace_column_memory",
    )
    op.drop_column("workspace_column_memory", "expires_at")

    op.drop_index("ix_refresh_sessions_expires_at", table_name="refresh_sessions")
    op.drop_index("ix_refresh_sessions_user_revoked", table_name="refresh_sessions")
    op.drop_index("ix_refresh_sessions_user_id", table_name="refresh_sessions")
    op.drop_index("ix_refresh_sessions_jti", table_name="refresh_sessions")
    op.drop_table("refresh_sessions")
