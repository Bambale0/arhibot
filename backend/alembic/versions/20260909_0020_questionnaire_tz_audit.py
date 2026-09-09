"""Publish questionnaire audit fixes.

Revision ID: 20260909_0020
Revises: 20260909_0019
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.questionnaires.catalog import _load_sources, build_catalog

revision: str = "20260909_0020"
down_revision: str | None = "20260909_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _catalog_table():
    return sa.table(
        "questionnaire_catalog_config",
        sa.column("id", sa.Integer()),
        sa.column("version", sa.String(length=64)),
        sa.column("catalog", postgresql.JSONB()),
        sa.column("source_texts", postgresql.JSONB()),
    )


def upgrade() -> None:
    catalog = build_catalog()
    table = _catalog_table()
    op.get_bind().execute(
        sa.update(table)
        .where(table.c.id == 1)
        .where(table.c.version == "2026-09-09.1")
        .values(
            version=catalog["version"],
            catalog=catalog,
            source_texts=_load_sources(),
        )
    )


def downgrade() -> None:
    # Runtime questionnaire content is operator-managed; do not overwrite it on rollback.
    pass
