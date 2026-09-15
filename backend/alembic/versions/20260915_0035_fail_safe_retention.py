"""Make retention/backup fail-safe and reserve media disk headroom.

Revision ID: 20260915_0035
Revises: 20260915_0034
Create Date: 2026-09-15
"""

from alembic import op
import sqlalchemy as sa

revision = "20260915_0035"
down_revision = "20260915_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE operational_settings
            SET media_retention_days = COALESCE(media_retention_days, 30),
                backup_interval_hours = COALESCE(backup_interval_hours, 24),
                backup_retention_days = COALESCE(backup_retention_days, 14)
            """
        )
    )
    for column, default in (
        ("media_retention_days", "30"),
        ("backup_interval_hours", "24"),
        ("backup_retention_days", "14"),
    ):
        op.alter_column(
            "operational_settings",
            column,
            existing_type=sa.Integer(),
            nullable=False,
            server_default=default,
        )

    op.add_column(
        "operational_settings",
        sa.Column(
            "media_min_free_bytes",
            sa.BigInteger(),
            nullable=False,
            server_default=str(2 * 1024 * 1024 * 1024),
        ),
    )


def downgrade() -> None:
    op.drop_column("operational_settings", "media_min_free_bytes")
    for column in (
        "backup_retention_days",
        "backup_interval_hours",
        "media_retention_days",
    ):
        op.alter_column(
            "operational_settings",
            column,
            existing_type=sa.Integer(),
            nullable=True,
            server_default=None,
        )
