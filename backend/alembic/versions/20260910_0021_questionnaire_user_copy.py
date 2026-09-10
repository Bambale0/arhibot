"""Publish user-facing questionnaire copy cleanup and preserve catalog revisions.

Revision ID: 20260910_0021
Revises: 20260909_0020
Create Date: 2026-09-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.questionnaires.catalog import build_catalog

revision: str = "20260910_0021"
down_revision: str | None = "20260909_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _catalog_table():
    return sa.table(
        "questionnaire_catalog_config",
        sa.column("id", sa.Integer()),
        sa.column("version", sa.String(length=64)),
        sa.column("catalog", postgresql.JSONB()),
    )


def upgrade() -> None:
    op.create_table(
        "questionnaire_catalog_revisions",
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("catalog", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_texts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("version"),
    )
    op.execute(
        sa.text(
            "INSERT INTO questionnaire_catalog_revisions (version, catalog, source_texts) "
            "SELECT version, catalog, source_texts FROM questionnaire_catalog_config WHERE id = 1 "
            "ON CONFLICT (version) DO NOTHING"
        )
    )

    catalog = build_catalog()
    table = _catalog_table()
    op.get_bind().execute(
        sa.update(table)
        .where(table.c.id == 1)
        .where(table.c.version == "2026-09-09.2")
        .values(version=catalog["version"], catalog=catalog)
    )
    op.execute(
        sa.text(
            "INSERT INTO questionnaire_catalog_revisions (version, catalog, source_texts) "
            "SELECT version, catalog, source_texts FROM questionnaire_catalog_config WHERE id = 1 "
            "ON CONFLICT (version) DO NOTHING"
        )
    )


def downgrade() -> None:
    # Runtime questionnaire content is operator-managed; do not overwrite it on rollback.
    op.drop_table("questionnaire_catalog_revisions")
