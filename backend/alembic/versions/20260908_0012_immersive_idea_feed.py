"""Immersive idea feed media and architecture snapshot

Revision ID: 20260908_0012
Revises: 20260905_0011
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260908_0012"
down_revision: str | None = "20260905_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "idea_templates",
        sa.Column(
            "media_items",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "idea_templates",
        sa.Column("architecture_project_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_idea_templates_architecture_project_id_projects",
        "idea_templates",
        "projects",
        ["architecture_project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "idea_templates",
        sa.Column("architecture_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    # Existing published generation assets inherit a safe snapshot of their project's
    # canonical architecture. This copies related data only; no business values are seeded.
    op.execute(
        sa.text(
            """
            UPDATE idea_templates AS idea
               SET architecture_project_id = project.id,
                   architecture_snapshot = project.context -> 'architecture'
              FROM assets AS asset
              JOIN projects AS project ON project.id = asset.project_id
             WHERE idea.image_asset_id = asset.id
               AND project.context ? 'architecture'
               AND jsonb_typeof(project.context -> 'architecture') = 'object'
            """
        )
    )


def downgrade() -> None:
    op.drop_column("idea_templates", "architecture_snapshot")
    op.drop_constraint(
        "fk_idea_templates_architecture_project_id_projects",
        "idea_templates",
        type_="foreignkey",
    )
    op.drop_column("idea_templates", "architecture_project_id")
    op.drop_column("idea_templates", "media_items")
