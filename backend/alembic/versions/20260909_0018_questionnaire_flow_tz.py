"""Publish the approved questionnaire-flow catalog revision.

Revision ID: 20260909_0018
Revises: 20260909_0017
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.questionnaires.catalog import _load_sources, build_catalog

revision: str = "20260909_0018"
down_revision: str | None = "20260909_0017"
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
    catalog_table = _catalog_table()
    bind = op.get_bind()
    bind.execute(
        sa.update(catalog_table)
        .where(catalog_table.c.id == 1)
        .values(
            version=catalog["version"],
            catalog=catalog,
            source_texts=_load_sources(),
        )
    )


def downgrade() -> None:
    # Questionnaire content is operator-managed after bootstrap. Reverting code
    # must not silently overwrite a newer runtime catalog with stale content.
    pass
