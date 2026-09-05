"""DB-backed operational settings

Revision ID: 20260905_0010
Revises: 20260905_0009
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260905_0010"
down_revision: str | None = "20260905_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operational_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("auth_rate_limit_per_minute", sa.Integer(), nullable=True),
        sa.Column("generation_rate_limit_per_minute", sa.Integer(), nullable=True),
        sa.Column("payment_rate_limit_per_minute", sa.Integer(), nullable=True),
        sa.Column("media_retention_days", sa.Integer(), nullable=True),
        sa.Column("backup_retention_days", sa.Integer(), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(sa.text("INSERT INTO operational_settings (id) VALUES (1)"))


def downgrade() -> None:
    op.drop_table("operational_settings")
