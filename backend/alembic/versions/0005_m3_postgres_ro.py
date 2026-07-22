"""M3: source_config_json on datasets for postgres_ro allowlist metadata.

Revision ID: 0005_m3_postgres_ro
Revises: 0004_m2_run_lifecycle
Create Date: 2026-07-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_m3_postgres_ro"
down_revision: Union[str, Sequence[str], None] = "0004_m2_run_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "datasets",
        sa.Column(
            "source_config_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("datasets", "source_config_json")
