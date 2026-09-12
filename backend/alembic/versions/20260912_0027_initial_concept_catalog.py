"""Publish the initial-concept questionnaire catalog contract.

Revision ID: 20260912_0027
Revises: 20260911_0026
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.questionnaires.catalog import _load_sources, build_catalog

revision: str = "20260912_0027"
down_revision: str | None = "20260911_0026"
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
    table = _catalog_table()
    current = op.get_bind().execute(
        sa.select(table.c.version, table.c.catalog, table.c.source_texts).where(table.c.id == 1)
    ).mappings().one_or_none()
    if current is None:
        return

    revisions = _revision_table()
    op.get_bind().execute(
        postgresql.insert(revisions)
        .values(
            version=current["version"],
            catalog=current["catalog"],
            source_texts=current["source_texts"],
        )
        .on_conflict_do_nothing(index_elements=["version"])
    )

    catalog = build_catalog()
    if current["version"] == "2026-09-10.1":
        op.get_bind().execute(
            sa.update(table)
            .where(table.c.id == 1)
            .values(
                version=catalog["version"],
                catalog=catalog,
                source_texts=_load_sources(),
            )
        )
        op.get_bind().execute(
            postgresql.insert(revisions)
            .values(
                version=catalog["version"],
                catalog=catalog,
                source_texts=_load_sources(),
            )
            .on_conflict_do_nothing(index_elements=["version"])
        )


def downgrade() -> None:
    # Questionnaire content is operator-managed; rollback must not overwrite runtime edits.
    pass
