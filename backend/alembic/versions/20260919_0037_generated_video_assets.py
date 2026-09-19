"""Add generated video asset type.

Revision ID: 20260919_0037
Revises: 20260915_0036
Create Date: 2026-09-19
"""

from alembic import op

revision = "20260919_0037"
down_revision = "20260915_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE asset_type ADD VALUE IF NOT EXISTS 'video'")


def downgrade() -> None:
    # PostgreSQL cannot safely remove an enum value while retained video rows may exist.
    # Keep the additive value on downgrade; application rollback remains backward compatible.
    pass
