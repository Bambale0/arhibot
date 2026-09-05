"""YooKassa receipt settings and full refund state

Revision ID: 20260905_0007
Revises: 20260905_0006
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260905_0007"
down_revision: str | None = "20260905_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "billing_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("receipts_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("vat_code", sa.Integer(), nullable=True),
        sa.Column("payment_subject", sa.String(length=64), nullable=True),
        sa.Column("payment_mode", sa.String(length=64), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("vat_code IS NULL OR (vat_code >= 1 AND vat_code <= 12)", name="ck_billing_settings_vat_code"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column("billing_payments", sa.Column("receipt_email", sa.String(length=320), nullable=True))
    op.add_column("billing_payments", sa.Column("refund_id", sa.String(length=64), nullable=True))
    op.add_column("billing_payments", sa.Column("refund_status", sa.String(length=32), nullable=True))
    op.add_column("billing_payments", sa.Column("refund_idempotence_key", sa.String(length=64), nullable=True))
    op.add_column("billing_payments", sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint("uq_billing_payments_refund_id", "billing_payments", ["refund_id"])
    op.create_unique_constraint(
        "uq_billing_payments_refund_idempotence_key",
        "billing_payments",
        ["refund_idempotence_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_billing_payments_refund_idempotence_key", "billing_payments", type_="unique")
    op.drop_constraint("uq_billing_payments_refund_id", "billing_payments", type_="unique")
    op.drop_column("billing_payments", "refunded_at")
    op.drop_column("billing_payments", "refund_idempotence_key")
    op.drop_column("billing_payments", "refund_status")
    op.drop_column("billing_payments", "refund_id")
    op.drop_column("billing_payments", "receipt_email")
    op.drop_table("billing_settings")
