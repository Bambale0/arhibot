"""Add concept video generation and runtime controls.

Revision ID: 20261005_0040
Revises: 20261003_0039
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261005_0040"
down_revision: str | None = "20261003_0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE asset_type ADD VALUE IF NOT EXISTS 'video'")
    op.execute("ALTER TYPE generation_type ADD VALUE IF NOT EXISTS 'video'")

    op.add_column(
        "generation_runtime_settings",
        sa.Column(
            "quality_judge_model",
            sa.String(length=120),
            nullable=True,
            server_default="grok-4.5",
        ),
    )
    op.add_column(
        "generation_runtime_settings",
        sa.Column(
            "video_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "generation_runtime_settings",
        sa.Column(
            "video_model",
            sa.String(length=120),
            nullable=True,
            server_default="seedance-2.0",
        ),
    )
    op.add_column(
        "generation_runtime_settings",
        sa.Column(
            "video_params",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    video_generations = bind.execute(
        sa.text("SELECT count(*) FROM generations WHERE type::text = 'video'")
    ).scalar_one()
    video_assets = bind.execute(
        sa.text("SELECT count(*) FROM assets WHERE type::text = 'video'")
    ).scalar_one()
    if video_generations or video_assets:
        raise RuntimeError(
            "Cannot downgrade concept-video migration while video generations/assets exist."
        )

    op.drop_column("generation_runtime_settings", "video_params")
    op.drop_column("generation_runtime_settings", "video_model")
    op.drop_column("generation_runtime_settings", "video_enabled")
    op.drop_column("generation_runtime_settings", "quality_judge_model")

    op.execute("ALTER TABLE assets ALTER COLUMN type DROP DEFAULT")
    op.execute("ALTER TABLE assets ALTER COLUMN type TYPE varchar USING type::text")
    op.execute("DROP TYPE asset_type")
    op.execute("CREATE TYPE asset_type AS ENUM ('image')")
    op.execute(
        "ALTER TABLE assets ALTER COLUMN type TYPE asset_type "
        "USING type::asset_type"
    )
    op.execute(
        "ALTER TABLE assets ALTER COLUMN type SET DEFAULT 'image'::asset_type"
    )

    op.execute(
        "ALTER TABLE generations ALTER COLUMN type TYPE varchar USING type::text"
    )
    op.execute("DROP TYPE generation_type")
    op.execute(
        "CREATE TYPE generation_type AS ENUM "
        "('floor_plan','facade','master_plan','interior')"
    )
    op.execute(
        "ALTER TABLE generations ALTER COLUMN type TYPE generation_type "
        "USING type::generation_type"
    )
