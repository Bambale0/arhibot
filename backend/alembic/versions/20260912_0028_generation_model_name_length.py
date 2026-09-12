"""Allow longer provider model identifiers on generation records.

Revision ID: 20260912_0028
Revises: 20260912_0027
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260912_0028"
down_revision: str | None = "20260912_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "generations",
        "model_name",
        existing_type=sa.String(length=80),
        type_=sa.String(length=120),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "generations",
        "model_name",
        existing_type=sa.String(length=120),
        type_=sa.String(length=80),
        existing_nullable=True,
    )
