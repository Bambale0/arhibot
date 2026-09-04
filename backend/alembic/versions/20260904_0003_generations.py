"""generation queue records

Revision ID: 20260904_0003
Revises: 20260903_0002
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260904_0003"
down_revision: str | None = "20260903_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    generation_type = postgresql.ENUM(
        "floor_plan",
        "facade",
        "master_plan",
        "interior",
        name="generation_type",
        create_type=False,
    )
    generation_status = postgresql.ENUM(
        "queued",
        "processing",
        "completed",
        "failed",
        name="generation_status",
        create_type=False,
    )
    generation_type.create(op.get_bind(), checkfirst=True)
    generation_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "generations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("input_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("output_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("type", generation_type, nullable=False),
        sa.Column("status", generation_status, server_default="queued", nullable=False),
        sa.Column("prompt", sa.Text(), server_default="", nullable=False),
        sa.Column("model_name", sa.String(length=80), nullable=True),
        sa.Column("fallback_used", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("provider_task_id", sa.String(length=120), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["input_asset_id"], ["assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["output_asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_generations_project_created", "generations", ["project_id", "created_at"])
    op.create_index("ix_generations_status_created", "generations", ["status", "created_at"])
    op.create_index("ix_generations_user_created", "generations", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_generations_user_created", table_name="generations")
    op.drop_index("ix_generations_status_created", table_name="generations")
    op.drop_index("ix_generations_project_created", table_name="generations")
    op.drop_table("generations")
    postgresql.ENUM(name="generation_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="generation_type").drop(op.get_bind(), checkfirst=True)
