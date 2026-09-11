"""Persist owner publication state and saved Ideas across devices.

Revision ID: 20260911_0024
Revises: 20260910_0023
Create Date: 2026-09-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260911_0024"
down_revision: str | None = "20260910_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "idea_publications",
        sa.Column("owner_published", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "idea_saves",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idea_publication_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["idea_publication_id"], ["idea_publications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "idea_publication_id",
            name="uq_idea_saves_user_publication",
        ),
    )
    op.create_index(
        "ix_idea_saves_user_created",
        "idea_saves",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_idea_saves_user_created", table_name="idea_saves")
    op.drop_table("idea_saves")
    op.drop_column("idea_publications", "owner_published")
