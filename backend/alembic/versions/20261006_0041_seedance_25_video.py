"""Use Seedance 2.5 for locked concept-video frame mode.

Revision ID: 20261006_0041
Revises: 20261005_0040
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_0041"
down_revision: str | None = "20261005_0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "generation_runtime_settings",
        "video_model",
        server_default="seedance-2.5",
    )
    op.execute(
        sa.text(
            "UPDATE generation_runtime_settings "
            "SET video_model = 'seedance-2.5' "
            "WHERE video_model = 'seedance-2.0'"
        )
    )


def downgrade() -> None:
    op.alter_column(
        "generation_runtime_settings",
        "video_model",
        server_default="seedance-2.0",
    )
