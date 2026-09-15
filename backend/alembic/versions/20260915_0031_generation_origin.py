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
    # Existing internal rows were server-created before provenance existed.
    # Backfill once during migration; runtime logic must never infer origin from prompt text.
    op.execute(
        """
        UPDATE generations
        SET origin = 'questionnaire'
        WHERE prompt LIKE 'AUROOM_RENDER_SPEC_V1%'
           OR prompt LIKE 'AUROOM_INITIAL_CONCEPT_V1%'
        """
    )
    op.execute(
        """
        UPDATE generations
        SET origin = 'admin_sandbox'
        WHERE prompt LIKE 'AUROOM_ADMIN_SANDBOX_V1%'
        """
    )
    op.execute(
        """
        UPDATE generations
        SET origin = 'admin_orbit'
        WHERE prompt LIKE 'AUROOM_ADMIN_ORBIT_V1%'
        """
    )
    op.create_index(
        "ix_generations_origin_created",
        "generations",
        ["origin", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_generations_origin_created", table_name="generations")
    op.drop_column("generations", "origin")
