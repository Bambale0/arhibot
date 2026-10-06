"""Default concept-video previews to 480p.

Revision ID: 20261006_0042
Revises: 20261006_0041
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_0042"
down_revision: str | None = "20261006_0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE generation_runtime_settings "
            "SET video_params = jsonb_set("
            "COALESCE(video_params, '{}'::jsonb), "
            "'{resolution}', to_jsonb('480p'::text), true"
            ") "
            "WHERE video_model = 'seedance-2.5' "
            "AND COALESCE(video_params->>'resolution', '') <> '480p'"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE generation_runtime_settings "
            "SET video_params = jsonb_set("
            "COALESCE(video_params, '{}'::jsonb), "
            "'{resolution}', to_jsonb('1080p'::text), true"
            ") "
            "WHERE video_model = 'seedance-2.5' "
            "AND video_params->>'resolution' = '480p'"
        )
    )
