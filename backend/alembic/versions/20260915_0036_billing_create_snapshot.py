"""Persist immutable YooKassa create request snapshots.

Revision ID: 20260915_0036
Revises: 20260915_0035
Create Date: 2026-09-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260915_0036"
down_revision = "20260915_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "billing_payments",
        sa.Column("create_request_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("billing_payments", "create_request_snapshot")
