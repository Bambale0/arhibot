"""billing payments and user credits

Revision ID: 20260904_0004
Revises: 20260904_0003
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260904_0004"
down_revision: str | None = "20260904_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("credits_balance", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "billing_payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("package_code", sa.String(length=64), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("amount_value", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="RUB", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("yookassa_payment_id", sa.String(length=64), nullable=True),
        sa.Column("idempotence_key", sa.String(length=64), nullable=False),
        sa.Column("confirmation_url", sa.Text(), nullable=True),
        sa.Column("provider_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotence_key", name="uq_billing_payments_idempotence_key"),
        sa.UniqueConstraint("yookassa_payment_id", name="uq_billing_payments_yookassa_id"),
    )
    op.create_index(
        "ix_billing_payments_user_created",
        "billing_payments",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_billing_payments_user_created", table_name="billing_payments")
    op.drop_table("billing_payments")
    op.drop_column("users", "credits_balance")
