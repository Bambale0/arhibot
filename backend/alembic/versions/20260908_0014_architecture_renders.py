"""Architecture render jobs

Revision ID: 20260908_0014
Revises: 20260908_0013
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260908_0014"
down_revision: str | None = "20260908_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


render_status = postgresql.ENUM(
    "queued",
    "processing",
    "completed",
    "failed",
    name="architecture_render_status",
    create_type=False,
)


def upgrade() -> None:
    render_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "architecture_renders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", render_status, server_default="queued", nullable=False),
        sa.Column("architecture", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "renderer_profile",
            sa.String(length=80),
            server_default="blender_eevee_v1",
            nullable=False,
        ),
        sa.Column("renderer_version", sa.String(length=120), nullable=True),
        sa.Column("storage_path", sa.String(length=512), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_path"),
    )
    op.create_index(
        "ix_architecture_renders_user_created",
        "architecture_renders",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_architecture_renders_project_created",
        "architecture_renders",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_architecture_renders_status_created",
        "architecture_renders",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_architecture_renders_status_created", table_name="architecture_renders")
    op.drop_index("ix_architecture_renders_project_created", table_name="architecture_renders")
    op.drop_index("ix_architecture_renders_user_created", table_name="architecture_renders")
    op.drop_table("architecture_renders")
    render_status.drop(op.get_bind(), checkfirst=True)
