"""DB-backed Telegram bot content

Revision ID: 20260905_0011
Revises: 20260905_0010
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260905_0011"
down_revision: str | None = "20260905_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_content_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bot_name", sa.String(length=64), nullable=True),
        sa.Column("short_description", sa.String(length=120), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_text", sa.Text(), nullable=True),
        sa.Column("open_button_text", sa.String(length=64), nullable=True),
        sa.Column("start_command_description", sa.String(length=256), nullable=True),
        sa.Column("app_command_description", sa.String(length=256), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    # Structural singleton only: business copy is populated through the control plane.
    op.execute(sa.text("INSERT INTO telegram_content_settings (id) VALUES (1)"))


def downgrade() -> None:
    op.drop_table("telegram_content_settings")
