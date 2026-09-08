"""Exact GLB models for immersive idea feed

Revision ID: 20260908_0013
Revises: 20260908_0012
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260908_0013"
down_revision: str | None = "20260908_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("idea_templates", sa.Column("model_storage_path", sa.String(length=512), nullable=True))
    op.add_column("idea_templates", sa.Column("model_original_filename", sa.String(length=255), nullable=True))
    op.add_column("idea_templates", sa.Column("model_size_bytes", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("idea_templates", "model_size_bytes")
    op.drop_column("idea_templates", "model_original_filename")
    op.drop_column("idea_templates", "model_storage_path")
