"""Store the production primary-generation failover timeout in admin settings.

Revision ID: 20260914_0029
Revises: 20260912_0028
Create Date: 2026-09-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260914_0029"
down_revision: str | None = "20260912_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "generation_runtime_settings",
        sa.Column(
            "primary_timeout_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("90"),
        ),
    )


def downgrade() -> None:
    op.drop_column("generation_runtime_settings", "primary_timeout_seconds")
