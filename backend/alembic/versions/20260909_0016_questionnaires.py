"""Questionnaire catalog control plane and applications.

Revision ID: 20260909_0016
Revises: 20260908_0015
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.questionnaires.catalog import _load_sources, build_catalog

revision: str = "20260909_0016"
down_revision: str | None = "20260908_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "questionnaire_catalog_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("catalog", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_texts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "questionnaire_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("catalog_version", sa.String(length=64), nullable=False),
        sa.Column("selected_objects", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("accepted_objects", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("answers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("scene_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="new", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scene_asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_questionnaire_applications_session_id"),
    )
    op.create_index(
        "ix_questionnaire_applications_created_at",
        "questionnaire_applications",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_questionnaire_applications_project_id",
        "questionnaire_applications",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_questionnaire_applications_status_created",
        "questionnaire_applications",
        ["status", "created_at"],
        unique=False,
    )

    catalog = build_catalog()
    source_texts = _load_sources()
    catalog_table = sa.table(
        "questionnaire_catalog_config",
        sa.column("id", sa.Integer()),
        sa.column("version", sa.String(length=64)),
        sa.column("catalog", postgresql.JSONB()),
        sa.column("source_texts", postgresql.JSONB()),
    )
    op.bulk_insert(
        catalog_table,
        [
            {
                "id": 1,
                "version": catalog["version"],
                "catalog": catalog,
                "source_texts": source_texts,
            }
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_questionnaire_applications_status_created",
        table_name="questionnaire_applications",
    )
    op.drop_index(
        "ix_questionnaire_applications_project_id",
        table_name="questionnaire_applications",
    )
    op.drop_index(
        "ix_questionnaire_applications_created_at",
        table_name="questionnaire_applications",
    )
    op.drop_table("questionnaire_applications")
    op.drop_table("questionnaire_catalog_config")
