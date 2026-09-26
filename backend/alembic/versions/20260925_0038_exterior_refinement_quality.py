"""Add exterior refinement policy and quality controls.

Revision ID: 20260925_0038
Revises: 20260916_0037
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.questionnaires.catalog import _load_sources, build_catalog

revision: str = "20260925_0038"
down_revision: str | Sequence[str] | None = "20260916_0037"
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
    op.add_column(
        "generations",
        sa.Column(
            "edit_policy",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "generations",
        sa.Column("quality_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "generations",
        sa.Column("quality_status", sa.String(length=32), nullable=True),
    )

    runtime_columns = (
        ("masked_edit_provider_context_margin_fraction", sa.Float(), "0.03"),
        ("masked_edit_feather_fraction", sa.Float(), "0.014"),
        ("masked_edit_feather_min_px", sa.Integer(), "4"),
        ("masked_edit_feather_max_px", sa.Integer(), "24"),
        ("masked_edit_recomposite_feather_multiplier", sa.Float(), "1.75"),
        ("masked_edit_boundary_band_px", sa.Integer(), "4"),
        ("masked_edit_max_luma_excess", sa.Float(), "20"),
        ("masked_edit_max_color_excess", sa.Float(), "32"),
        ("masked_edit_max_straight_edge_fraction", sa.Float(), "0.65"),
        ("generation_quality_max_retries", sa.Integer(), "1"),
    )
    for name, column_type, default in runtime_columns:
        op.add_column(
            "generation_runtime_settings",
            sa.Column(name, column_type, server_default=default, nullable=False),
        )

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

    if current["version"] == "2026-09-12.1":
        catalog = build_catalog()
        sources = _load_sources()
        op.get_bind().execute(
            sa.update(table)
            .where(table.c.id == 1)
            .values(version=catalog["version"], catalog=catalog, source_texts=sources)
        )
        op.get_bind().execute(
            postgresql.insert(revisions)
            .values(version=catalog["version"], catalog=catalog, source_texts=sources)
            .on_conflict_do_nothing(index_elements=["version"])
        )


def downgrade() -> None:
    # Questionnaire catalog content is operator-managed; never overwrite it on rollback.
    for name in (
        "generation_quality_max_retries",
        "masked_edit_max_straight_edge_fraction",
        "masked_edit_max_color_excess",
        "masked_edit_max_luma_excess",
        "masked_edit_boundary_band_px",
        "masked_edit_recomposite_feather_multiplier",
        "masked_edit_feather_max_px",
        "masked_edit_feather_min_px",
        "masked_edit_feather_fraction",
        "masked_edit_provider_context_margin_fraction",
    ):
        op.drop_column("generation_runtime_settings", name)
    op.drop_column("generations", "quality_status")
    op.drop_column("generations", "quality_report")
    op.drop_column("generations", "edit_policy")
