"""idea feed image assets

Revision ID: 20260905_0008
Revises: 20260905_0007
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260905_0008"
down_revision: str | None = "20260905_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "idea_templates",
        sa.Column("image_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_idea_templates_image_asset",
        "idea_templates",
        "assets",
        ["image_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_idea_templates_image_asset_id", "idea_templates", ["image_asset_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_idea_templates_image_asset_id", table_name="idea_templates")
    op.drop_constraint("fk_idea_templates_image_asset", "idea_templates", type_="foreignkey")
    op.drop_column("idea_templates", "image_asset_id")
