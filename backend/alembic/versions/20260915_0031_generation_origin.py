"""Add server-owned generation provenance.

Revision ID: 20260915_0031
Revises: 20260914_0030
Create Date: 2026-09-15
"""

from alembic import op
import sqlalchemy as sa

revision = "20260915_0031"
down_revision = "20260914_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "generations",
        sa.Column(
            "origin",
            sa.String(length=32),
            nullable=False,
            server_default="generic",
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE generations
            SET origin = CASE
                WHEN prompt LIKE 'AUROOM_ADMIN_SANDBOX_V1%' THEN 'admin_sandbox'
                WHEN prompt LIKE 'AUROOM_ADMIN_ORBIT_V1%' THEN 'admin_orbit'
                WHEN prompt LIKE 'AUROOM_INITIAL_CONCEPT_V1%' THEN 'questionnaire_initial'
                WHEN prompt LIKE 'AUROOM_RENDER_SPEC_V1%' THEN 'questionnaire'
                ELSE 'generic'
            END
            """
        )
    )
    op.create_index(
        "ix_generations_project_origin_created",
        "generations",
        ["project_id", "origin", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_generations_project_origin_created", table_name="generations")
    op.drop_column("generations", "origin")
