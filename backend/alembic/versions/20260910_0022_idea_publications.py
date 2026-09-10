"""Publish accepted generated works in the Ideas feed.

Revision ID: 20260910_0022
Revises: 20260910_0021
Create Date: 2026-09-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260910_0022"
down_revision: str | None = "20260910_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "idea_publications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("published_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("presentation_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["generation_id"], ["generations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["published_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("generation_id", name="uq_idea_publications_generation_id"),
    )
    op.create_index(
        "ix_idea_publications_active_order",
        "idea_publications",
        ["is_active", "sort_order", "created_at"],
        unique=False,
    )

    # Legacy manually-authored rows remain untouched for audit/rollback. New API/UI
    # routes read only idea_publications, so legacy rows are inert without mutating
    # operator-managed historical data.


def downgrade() -> None:
    op.drop_index("ix_idea_publications_active_order", table_name="idea_publications")
    op.drop_table("idea_publications")
