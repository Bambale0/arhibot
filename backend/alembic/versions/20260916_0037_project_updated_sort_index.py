"""Index project listing by last update time.

Revision ID: 20260916_0037
Revises: 20260915_0036
Create Date: 2026-09-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260916_0037"
down_revision: str | Sequence[str] | None = "20260915_0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_projects_user_updated",
        "projects",
        ["user_id", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_projects_user_updated", table_name="projects")
