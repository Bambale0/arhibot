"""generation pricing and immutable credit ledger

Revision ID: 20260905_0006
Revises: 20260905_0005
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260905_0006"
down_revision: str | None = "20260905_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "generation_credit_prices",
        sa.Column("generation_type", sa.String(length=32), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("credits > 0", name="ck_generation_credit_prices_positive"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("generation_type"),
    )

    op.create_table(
        "credit_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=48), nullable=False),
        sa.Column("reference_type", sa.String(length=48), nullable=True),
        sa.Column("reference_id", sa.String(length=120), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=180), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount <> 0", name="ck_credit_transactions_nonzero"),
        sa.CheckConstraint("balance_after >= 0", name="ck_credit_transactions_balance_nonnegative"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_credit_transactions_idempotency_key"),
    )
    op.create_index(
        "ix_credit_transactions_user_created",
        "credit_transactions",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_credit_transactions_reference",
        "credit_transactions",
        ["reference_type", "reference_id"],
        unique=False,
    )

    op.alter_column("generations", "input_asset_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.add_column(
        "generations",
        sa.Column("credits_charged", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("generations", "credits_charged")
    op.alter_column("generations", "input_asset_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    op.drop_index("ix_credit_transactions_reference", table_name="credit_transactions")
    op.drop_index("ix_credit_transactions_user_created", table_name="credit_transactions")
    op.drop_table("credit_transactions")
    op.drop_table("generation_credit_prices")
