"""Architecture render batches and Idea publication

Revision ID: 20260908_0016
Revises: 20260908_0015
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260908_0016"
down_revision: str | None = "20260908_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # PostgreSQL enum value removal is deliberately not attempted on downgrade. The value is
    # backward-compatible and keeping it avoids rewriting the entire enum type during rollback.
    op.execute("ALTER TYPE asset_purpose ADD VALUE IF NOT EXISTS 'architecture_render_output'")
    op.add_column(
        "architecture_renders",
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "architecture_renders",
        sa.Column("target_idea_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "architecture_renders",
        sa.Column("output_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "architecture_renders",
        sa.Column("quality_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "architecture_renders",
        sa.Column("quality_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "architecture_renders",
        sa.Column("selected_for_batch", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_foreign_key(
        "fk_architecture_renders_target_idea",
        "architecture_renders",
        "idea_templates",
        ["target_idea_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_architecture_renders_output_asset",
        "architecture_renders",
        "assets",
        ["output_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_architecture_renders_batch_created",
        "architecture_renders",
        ["batch_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_architecture_renders_batch_created", table_name="architecture_renders")
    op.drop_constraint(
        "fk_architecture_renders_output_asset",
        "architecture_renders",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_architecture_renders_target_idea",
        "architecture_renders",
        type_="foreignkey",
    )
    op.drop_column("architecture_renders", "selected_for_batch")
    op.drop_column("architecture_renders", "quality_report")
    op.drop_column("architecture_renders", "quality_score")
    op.drop_column("architecture_renders", "output_asset_id")
    op.drop_column("architecture_renders", "target_idea_id")
    op.drop_column("architecture_renders", "batch_id")
