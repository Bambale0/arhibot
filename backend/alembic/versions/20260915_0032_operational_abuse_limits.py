"""Add DB-managed abuse rate limits.

Revision ID: 20260915_0032
Revises: 20260915_0031
Create Date: 2026-09-15
"""

from alembic import op
import sqlalchemy as sa

revision = "20260915_0032"
down_revision = "20260915_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "operational_settings",
        sa.Column(
            "registration_rate_limit_per_day",
            sa.Integer(),
            nullable=True,
            server_default="20",
        ),
    )
    op.add_column(
        "operational_settings",
        sa.Column(
            "yookassa_webhook_rate_limit_per_minute",
            sa.Integer(),
            nullable=True,
            server_default="120",
        ),
    )


def downgrade() -> None:
    op.drop_column("operational_settings", "yookassa_webhook_rate_limit_per_minute")
    op.drop_column("operational_settings", "registration_rate_limit_per_day")
