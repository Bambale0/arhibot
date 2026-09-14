"""Add configurable initial questionnaire concept pricing.

Revision ID: 20260914_0030
Revises: 20260914_0029
Create Date: 2026-09-14
"""

from alembic import op
import sqlalchemy as sa

revision = "20260914_0030"
down_revision = "20260914_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "operational_settings",
        sa.Column(
            "initial_concept_credits",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("operational_settings", "initial_concept_credits")
