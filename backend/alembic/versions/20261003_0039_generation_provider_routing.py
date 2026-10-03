"""Add operator-managed primary and fallback image provider routing.

Revision ID: 20261003_0039
Revises: 20260925_0038
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_0039"
down_revision: str | None = "20260925_0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for role in ("primary", "fallback"):
        op.add_column(
            "generation_runtime_settings",
            sa.Column(
                f"{role}_provider",
                sa.String(length=32),
                nullable=False,
                server_default="neironych",
            ),
        )
        op.create_check_constraint(
            f"ck_generation_runtime_{role}_provider",
            "generation_runtime_settings",
            f"{role}_provider IN ('nexus', 'neironych')",
        )
    op.execute(
        sa.text(
            """
            UPDATE generation_runtime_settings
            SET primary_provider = 'neironych',
                fallback_provider = 'neironych',
                primary_model = 'gpt-image-2.5-sunburst',
                primary_params = jsonb_build_object(
                    'size', '3840x2160',
                    'quality', 'high'
                ),
                fallback_model = NULL,
                fallback_params = '{}'::jsonb
            WHERE id = 1
            """
        )
    )


def downgrade() -> None:
    for role in ("fallback", "primary"):
        op.drop_constraint(
            f"ck_generation_runtime_{role}_provider",
            "generation_runtime_settings",
            type_="check",
        )
        op.drop_column("generation_runtime_settings", f"{role}_provider")
