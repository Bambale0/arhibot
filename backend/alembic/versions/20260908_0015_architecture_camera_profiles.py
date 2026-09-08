"""Architecture render camera profiles

Revision ID: 20260908_0015
Revises: 20260908_0014
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260908_0015"
down_revision: str | None = "20260908_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "architecture_renders",
        sa.Column(
            "camera_profile",
            sa.String(length=40),
            server_default="hero_corner",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("architecture_renders", "camera_profile")
