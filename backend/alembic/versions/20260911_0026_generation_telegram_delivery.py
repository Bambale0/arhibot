"""Track reliable Telegram delivery for completed generations.

Revision ID: 20260911_0026
Revises: 20260911_0025
Create Date: 2026-09-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260911_0026"
down_revision: str | None = "20260911_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing completed generations must not flood users when this feature ships.
    # They are backfilled as skipped; only rows created after the migration default to pending.
    op.add_column(
        "generations",
        sa.Column(
            "telegram_delivery_status",
            sa.String(length=32),
            nullable=False,
            server_default="skipped",
        ),
    )
    op.add_column(
        "generations",
        sa.Column(
            "telegram_delivery_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "generations",
        sa.Column("telegram_delivery_error", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "generations",
        sa.Column("telegram_notified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column(
        "generations",
        "telegram_delivery_status",
        existing_type=sa.String(length=32),
        server_default="pending",
        existing_nullable=False,
    )
    op.create_index(
        "ix_generations_telegram_delivery",
        "generations",
        ["telegram_delivery_status", "completed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_generations_telegram_delivery", table_name="generations")
    op.drop_column("generations", "telegram_notified_at")
    op.drop_column("generations", "telegram_delivery_error")
    op.drop_column("generations", "telegram_delivery_attempts")
    op.drop_column("generations", "telegram_delivery_status")
