"""Publish contact-copy clarification for questionnaire applications.

Revision ID: 20260911_0023
Revises: 20260910_0022
Create Date: 2026-09-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.questionnaires.catalog import _load_sources, build_catalog

revision: str = "20260911_0023"
down_revision: str | None = "20260910_0022"
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


def _revision_table():
    return sa.table(
        "questionnaire_catalog_revisions",
        sa.column("version", sa.String(length=64)),
        sa.column("catalog", postgresql.JSONB()),
        sa.column("source_texts", postgresql.JSONB()),
    )


def upgrade() -> None:
    bind = op.get_bind()
    table = _catalog_table()
    revision_table = _revision_table()

    current = bind.execute(
        sa.select(table.c.version, table.c.catalog, table.c.source_texts).where(table.c.id == 1)
    ).mappings().first()
    if current is None or current["version"] != "2026-09-10.1":
        return

    bind.execute(
        postgresql.insert(revision_table)
        .values(
            version=current["version"],
            catalog=current["catalog"],
            source_texts=current["source_texts"],
        )
        .on_conflict_do_nothing(index_elements=["version"])
    )

    catalog = build_catalog()
    bind.execute(
        sa.update(table)
        .where(table.c.id == 1)
        .where(table.c.version == "2026-09-10.1")
        .values(
            version=catalog["version"],
            catalog=catalog,
            source_texts=_load_sources(),
        )
    )
    bind.execute(
        postgresql.insert(revision_table)
        .values(
            version=catalog["version"],
            catalog=catalog,
            source_texts=_load_sources(),
        )
        .on_conflict_do_nothing(index_elements=["version"])
    )


def downgrade() -> None:
    # Questionnaire history is immutable. Rollback of application code must not
    # silently overwrite the currently published operator-managed catalog.
    pass
