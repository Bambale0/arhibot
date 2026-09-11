"""Track why an Ideas publication was deactivated.

Revision ID: 20260911_0025
Revises: 20260911_0024
Create Date: 2026-09-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260911_0025"
down_revision: str | None = "20260911_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "idea_publications",
        sa.Column("deactivation_source", sa.String(length=16), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE idea_publications AS publication
            SET deactivation_source = CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM admin_audit_log AS audit
                    WHERE audit.action = 'idea.moderate'
                      AND audit.entity_type = 'idea_publication'
                      AND audit.entity_id = CAST(publication.id AS text)
                      AND audit.details->'fields' ? 'is_active'
                )
                THEN 'admin'
                ELSE 'owner'
            END
            WHERE publication.is_active = false
            """
        )
    )


def downgrade() -> None:
    op.drop_column("idea_publications", "deactivation_source")
