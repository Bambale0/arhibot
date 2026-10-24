"""Publish stove heating wording while preserving operator catalog configuration."""

from copy import deepcopy

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261024_0043"
down_revision = "20261006_0042"
branch_labels = None
depends_on = None

VERSION = "2026-10-24.1"
LABEL = "Печное отопление, труба"


def _updated_content(catalog, source_texts):
    catalog, source_texts = deepcopy(catalog), deepcopy(source_texts)
    house = next(item for item in catalog["questionnaires"] if item["key"] == "eskez-doma")
    for question in house["questions"]:
        if question["id"] == "11б":
            question.update(
                text="Печное отопление?",
                kind="single",
                options=["Нет", "Да"],
                skip_default="Нет",
                condition=None,
                help=(
                    "Да — дымовая труба на крыше дома. Нет — дом без дымовой трубы. "
                    "Наружную печь или камин на участке не добавляем."
                ),
            )
        if question["id"] == "15б":
            for old in ("Камин, труба", "Дымоход / труба"):
                question["options"] = [
                    LABEL if item == old else item for item in question["options"]
                ]
                targets = question.get("edit_targets", {})
                if old in targets:
                    targets[LABEL] = targets.pop(old)
    source = source_texts.get("eskez-doma")
    if source:
        source["text"] = (
            source["text"]
            .replace("Будет ли камин в доме?", "Печное отопление?")
            .replace(
                "Да — на фасаде каминная труба. Где именно труба, не спрашиваем: как дверь и ворота.\n"
                "Где камин внутри — не спрашиваем.",
                "Да — на крыше дома должна быть дымовая труба печного отопления.\n"
                "Нет — дымовой трубы на доме быть не должно.\n"
                "Наружную печь или камин на участке не добавляем.",
            )
        )
    catalog["version"] = VERSION
    return catalog, source_texts


def upgrade():
    table = sa.table(
        "questionnaire_catalog_config",
        sa.column("id", sa.Integer()),
        sa.column("version", sa.String(64)),
        sa.column("catalog", postgresql.JSONB()),
        sa.column("source_texts", postgresql.JSONB()),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    revisions = sa.table(
        "questionnaire_catalog_revisions",
        sa.column("version", sa.String(64)),
        sa.column("catalog", postgresql.JSONB()),
        sa.column("source_texts", postgresql.JSONB()),
    )
    bind = op.get_bind()
    current = (
        bind.execute(sa.select(table).where(table.c.id == 1).with_for_update())
        .mappings()
        .one_or_none()
    )
    if current is None or current["version"] == VERSION:
        return
    bind.execute(
        postgresql.insert(revisions)
        .values(
            version=current["version"],
            catalog=current["catalog"],
            source_texts=current["source_texts"],
        )
        .on_conflict_do_nothing(index_elements=["version"])
    )
    catalog, sources = _updated_content(current["catalog"], current["source_texts"])
    # A version is immutable: an unexpected collision must fail rather than rewrite history.
    bind.execute(
        sa.insert(revisions).values(version=VERSION, catalog=catalog, source_texts=sources)
    )
    bind.execute(
        sa.update(table)
        .where(table.c.id == 1)
        .values(version=VERSION, catalog=catalog, source_texts=sources, updated_at=sa.func.now())
    )


def downgrade():
    # Content is operator managed; never overwrite runtime edits during rollback.
    pass
