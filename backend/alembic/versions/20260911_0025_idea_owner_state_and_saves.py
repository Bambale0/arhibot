"""Persist owner publication state and saved Ideas across devices.

Revision ID: 20260911_0025
Revises: 20260911_0024
Create Date: 2026-09-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260911_0025"
down_revision: str | None = "20260911_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "idea_publications",
        sa.Column("owner_published", sa.Boolean(), nullable=True),
    )
    op.execute(
        """
        UPDATE idea_publications AS publication
        SET owner_published = CASE
            WHEN publication.is_active THEN TRUE
            WHEN EXISTS (
                SELECT 1
                FROM admin_audit_log AS audit
                WHERE audit.action = 'idea.moderate'
                  AND audit.entity_type = 'idea_publication'
                  AND audit.entity_id = publication.id::text
                  AND COALESCE(audit.details->'fields', '[]'::jsonb) @> '["is_active"]'::jsonb
            ) THEN TRUE
            ELSE FALSE
        END
        """
    )
    op.alter_column(
        "idea_publications",
        "owner_published",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.true(),
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
