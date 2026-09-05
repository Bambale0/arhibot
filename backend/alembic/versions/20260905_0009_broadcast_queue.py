"""queued Telegram broadcasts with deliveries

Revision ID: 20260905_0009
Revises: 20260905_0008
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260905_0009"
down_revision: str | None = "20260905_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("broadcast_campaigns", sa.Column("segment", sa.String(length=32), server_default="all", nullable=False))
    op.add_column("broadcast_campaigns", sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("broadcast_campaigns", sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_broadcast_campaigns_status_schedule", "broadcast_campaigns", ["status", "scheduled_at"], unique=False)

    op.create_table(
        "broadcast_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["campaign_id"], ["broadcast_campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "recipient_id", name="uq_broadcast_delivery_campaign_recipient"),
    )
    op.create_index("ix_broadcast_deliveries_campaign_status", "broadcast_deliveries", ["campaign_id", "status"], unique=False)
    op.create_index("ix_broadcast_deliveries_retry", "broadcast_deliveries", ["status", "next_attempt_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_broadcast_deliveries_retry", table_name="broadcast_deliveries")
    op.drop_index("ix_broadcast_deliveries_campaign_status", table_name="broadcast_deliveries")
    op.drop_table("broadcast_deliveries")
    op.drop_index("ix_broadcast_campaigns_status_schedule", table_name="broadcast_campaigns")
    op.drop_column("broadcast_campaigns", "canceled_at")
    op.drop_column("broadcast_campaigns", "scheduled_at")
    op.drop_column("broadcast_campaigns", "segment")
