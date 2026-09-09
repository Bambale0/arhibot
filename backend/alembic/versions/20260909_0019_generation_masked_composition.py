"""Persist deterministic masked composition for image generations.

Revision ID: 20260909_0019
Revises: 20260909_0018
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260909_0019"
down_revision: str | None = "20260909_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "generations",
        sa.Column(
            "composition_mode",
            sa.String(length=32),
            server_default="replace",
            nullable=False,
        ),
    )
    op.add_column(
        "generations",
        sa.Column("edit_region", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "generations",
        sa.Column(
            "protected_regions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("generations", "protected_regions")
    op.drop_column("generations", "edit_region")
    op.drop_column("generations", "composition_mode")
