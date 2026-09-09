"""Track Telegram delivery for questionnaire applications.

Revision ID: 20260909_0017
Revises: 20260909_0016
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260909_0017"
down_revision: str | None = "20260909_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "questionnaire_applications",
        sa.Column(
            "telegram_delivery_status",
            sa.String(length=32),
            server_default="legacy",
            nullable=False,
        ),
    )
    op.add_column(
        "questionnaire_applications",
        sa.Column(
            "telegram_delivery_attempts",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "questionnaire_applications",
        sa.Column("telegram_delivery_error", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "questionnaire_applications",
        sa.Column("telegram_notified_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Existing rows (and any old-code writes during migration) are legacy. New-code
    # inserts after the migration receive the pending default and are delivered.
    op.alter_column(
        "questionnaire_applications",
        "telegram_delivery_status",
        existing_type=sa.String(length=32),
        server_default="pending",
        existing_nullable=False,
    )
    op.create_index(
        "ix_questionnaire_applications_telegram_delivery",
        "questionnaire_applications",
        ["telegram_delivery_status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_questionnaire_applications_telegram_delivery",
        table_name="questionnaire_applications",
    )
    op.drop_column("questionnaire_applications", "telegram_notified_at")
    op.drop_column("questionnaire_applications", "telegram_delivery_error")
    op.drop_column("questionnaire_applications", "telegram_delivery_attempts")
    op.drop_column("questionnaire_applications", "telegram_delivery_status")
