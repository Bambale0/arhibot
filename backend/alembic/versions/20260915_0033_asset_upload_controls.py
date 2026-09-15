"""Add production asset upload controls.

Revision ID: 20260915_0033
Revises: 20260915_0032
Create Date: 2026-09-15
"""

from alembic import op
import sqlalchemy as sa

revision = "20260915_0033"
down_revision = "20260915_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "operational_settings",
        sa.Column(
            "asset_upload_rate_limit_per_minute",
            sa.Integer(),
            nullable=False,
            server_default="12",
        ),
    )
    op.add_column(
        "operational_settings",
        sa.Column(
            "asset_max_retained_count_per_user",
            sa.Integer(),
            nullable=False,
            server_default="200",
        ),
    )
    op.add_column(
        "operational_settings",
        sa.Column(
            "asset_max_retained_bytes_per_user",
            sa.BigInteger(),
            nullable=False,
            server_default=str(512 * 1024 * 1024),
        ),
    )


def downgrade() -> None:
    op.drop_column("operational_settings", "asset_max_retained_bytes_per_user")
    op.drop_column("operational_settings", "asset_max_retained_count_per_user")
    op.drop_column("operational_settings", "asset_upload_rate_limit_per_minute")
