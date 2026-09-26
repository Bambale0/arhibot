"""Make critical runtime limits fail-safe and add generation fairness controls.

Revision ID: 20260915_0034
Revises: 20260915_0033
Create Date: 2026-09-15
"""

from alembic import op
import sqlalchemy as sa

revision = "20260915_0034"
down_revision = "20260915_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE operational_settings
            SET auth_rate_limit_per_minute = COALESCE(auth_rate_limit_per_minute, 30),
                generation_rate_limit_per_minute = COALESCE(generation_rate_limit_per_minute, 10),
                payment_rate_limit_per_minute = COALESCE(payment_rate_limit_per_minute, 10),
                registration_rate_limit_per_day = COALESCE(registration_rate_limit_per_day, 20),
                yookassa_webhook_rate_limit_per_minute = COALESCE(
                    yookassa_webhook_rate_limit_per_minute, 120
                )
            """
        )
    )
    for column, default in (
        ("auth_rate_limit_per_minute", "30"),
        ("generation_rate_limit_per_minute", "10"),
        ("payment_rate_limit_per_minute", "10"),
        ("registration_rate_limit_per_day", "20"),
        ("yookassa_webhook_rate_limit_per_minute", "120"),
    ):
        op.alter_column(
            "operational_settings",
            column,
            existing_type=sa.Integer(),
            nullable=False,
            server_default=default,
        )

    op.add_column(
        "operational_settings",
        sa.Column(
            "generation_max_inflight_per_user",
            sa.Integer(),
            nullable=False,
            server_default="2",
        ),
    )
    op.add_column(
        "operational_settings",
        sa.Column(
            "initial_concept_offer_limit_per_day",
            sa.Integer(),
            nullable=False,
            server_default="3",
        ),
    )


def downgrade() -> None:
    op.drop_column("operational_settings", "initial_concept_offer_limit_per_day")
    op.drop_column("operational_settings", "generation_max_inflight_per_user")
    for column in (
        "yookassa_webhook_rate_limit_per_minute",
        "registration_rate_limit_per_day",
        "payment_rate_limit_per_minute",
        "generation_rate_limit_per_minute",
        "auth_rate_limit_per_minute",
    ):
        op.alter_column(
            "operational_settings",
            column,
            existing_type=sa.Integer(),
            nullable=True,
            server_default=None,
        )
