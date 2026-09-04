"""projects and local image assets

Revision ID: 20260903_0002
Revises: 20260903_0001
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260903_0002"
down_revision: str | None = "20260903_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    project_status = postgresql.ENUM("active", "archived", name="project_status", create_type=False)
    asset_type = postgresql.ENUM("image", name="asset_type", create_type=False)
    asset_purpose = postgresql.ENUM(
        "generation_input",
        "project_reference",
        "generation_output",
        name="asset_purpose",
        create_type=False,
    )
    project_status.create(op.get_bind(), checkfirst=True)
    asset_type.create(op.get_bind(), checkfirst=True)
    asset_purpose.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", project_status, server_default="active", nullable=False),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_user_created", "projects", ["user_id", "created_at"], unique=False)
    op.create_index("ix_projects_user_deleted", "projects", ["user_id", "deleted_at"], unique=False)

    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("type", asset_type, server_default="image", nullable=False),
        sa.Column("purpose", asset_purpose, nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_path"),
    )
    op.create_index("ix_assets_project_id", "assets", ["project_id"], unique=False)
    op.create_index("ix_assets_user_created", "assets", ["user_id", "created_at"], unique=False)

    op.create_foreign_key(
        "fk_users_avatar_asset_id_assets",
        "users",
        "assets",
        ["avatar_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_avatar_asset_id_assets", "users", type_="foreignkey")
    op.drop_index("ix_assets_user_created", table_name="assets")
    op.drop_index("ix_assets_project_id", table_name="assets")
    op.drop_table("assets")
    op.drop_index("ix_projects_user_deleted", table_name="projects")
    op.drop_index("ix_projects_user_created", table_name="projects")
    op.drop_table("projects")

    postgresql.ENUM(name="asset_purpose").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="asset_type").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="project_status").drop(op.get_bind(), checkfirst=True)
