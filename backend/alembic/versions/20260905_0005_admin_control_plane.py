"""admin control plane and DB-backed business configuration

Revision ID: 20260905_0005
Revises: 20260904_0004
Create Date: 2026-09-05
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260905_0005"
down_revision: str | None = "20260904_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "billing_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("amount_value", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="RUB", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_billing_plans_code"),
    )
    op.create_index("ix_billing_plans_active_order", "billing_plans", ["is_active", "sort_order"], unique=False)

    op.create_table(
        "idea_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("generation_type", sa.String(length=32), nullable=False),
        sa.Column("prompt", sa.Text(), server_default="", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_idea_templates_active_order", "idea_templates", ["is_active", "sort_order"], unique=False)

    op.create_table(
        "generation_runtime_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("primary_model", sa.String(length=120), nullable=False),
        sa.Column("fallback_model", sa.String(length=120), nullable=True),
        sa.Column("primary_params", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("fallback_params", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("mode_params", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "generation_prompt_templates",
        sa.Column("generation_type", sa.String(length=32), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("generation_type"),
    )

    op.create_table(
        "broadcast_campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="draft", nullable=False),
        sa.Column("recipient_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sent_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_broadcast_campaigns_created_at", "broadcast_campaigns", ["created_at"], unique=False)

    op.create_table(
        "admin_audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=120), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admin_audit_log_created_at", "admin_audit_log", ["created_at"], unique=False)

    settings_table = sa.table(
        "generation_runtime_settings",
        sa.column("id", sa.Integer()),
        sa.column("primary_model", sa.String()),
        sa.column("fallback_model", sa.String()),
        sa.column("primary_params", postgresql.JSONB()),
        sa.column("fallback_params", postgresql.JSONB()),
        sa.column("mode_params", postgresql.JSONB()),
    )
    op.bulk_insert(
        settings_table,
        [
            {
                "id": 1,
                "primary_model": "nano-banana-pro",
                "fallback_model": "gpt-image-2",
                "primary_params": {"image_size": "2K"},
                "fallback_params": {},
                "mode_params": {
                    "floor_plan": {"aspect_ratio": "1:1"},
                    "facade": {"aspect_ratio": "16:9"},
                    "master_plan": {"aspect_ratio": "1:1"},
                    "interior": {"aspect_ratio": "16:9"},
                },
            }
        ],
    )

    prompt_table = sa.table(
        "generation_prompt_templates",
        sa.column("generation_type", sa.String()),
        sa.column("template", sa.Text()),
    )
    base = (
        "Create a realistic, professional architectural visualization. Preserve useful geometry from the reference image "
        "unless the scenario explicitly requires a new plan. No text, logos, watermarks, UI, people, or decorative labels."
    )
    prompts = {
        "floor_plan": "Create a clean top-down residential floor plan concept. Prioritize functional zoning, comfortable circulation, realistic room proportions, daylight access and buildable logic.",
        "facade": "Redesign the exterior facade of the referenced house while preserving its main massing, openings and camera viewpoint. Produce a photorealistic architectural exterior.",
        "master_plan": "Create a coherent top-down master plan for the site: house placement, access, parking, paths, private outdoor zones and landscaping. Keep the result visually clear and realistic.",
        "interior": "Redesign the referenced room while preserving its structural geometry and camera viewpoint. Produce a photorealistic interior with practical furniture placement and realistic lighting.",
    }
    op.bulk_insert(
        prompt_table,
        [
            {
                "generation_type": mode,
                "template": f"{base}\n\n{instruction}\n\nProject context: {{project_context}}\n\nClient preferences: {{user_prompt}}",
            }
            for mode, instruction in prompts.items()
        ],
    )

    idea_table = sa.table(
        "idea_templates",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("title", sa.String()),
        sa.column("category", sa.String()),
        sa.column("text", sa.Text()),
        sa.column("generation_type", sa.String()),
        sa.column("prompt", sa.Text()),
        sa.column("is_active", sa.Boolean()),
        sa.column("sort_order", sa.Integer()),
    )
    initial_ideas = [
        ("Семейный дом 140 м²", "ПЛАНИРОВКА", "3 спальни, кухня-гостиная, мастер-блок и компактная постирочная.", "floor_plan"),
        ("Тёплый минимализм", "ФАСАД", "Штукатурка, дерево, графитовые рамы и мягкая архитектурная подсветка.", "facade"),
        ("Участок 12 соток", "МАСТЕР-ПЛАН", "Дом, баня, парковка, терраса и приватная зона сада.", "master_plan"),
        ("Гостиная с кухней", "ИНТЕРЬЕР", "Натуральный камень, дуб, спокойный свет и чистая геометрия.", "interior"),
        ("Дом с плоской кровлей", "ФАСАД", "Контраст светлого объёма и тёмного цоколя с крупным остеклением.", "facade"),
        ("Спальня в спокойной палитре", "ИНТЕРЬЕР", "Мягкие фактуры, скрытый свет и акцентное изголовье.", "interior"),
    ]
    op.bulk_insert(
        idea_table,
        [
            {
                "id": uuid4(),
                "title": title,
                "category": category,
                "text": text,
                "generation_type": mode,
                "prompt": text,
                "is_active": True,
                "sort_order": index,
            }
            for index, (title, category, text, mode) in enumerate(initial_ideas)
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_admin_audit_log_created_at", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")
    op.drop_index("ix_broadcast_campaigns_created_at", table_name="broadcast_campaigns")
    op.drop_table("broadcast_campaigns")
    op.drop_table("generation_prompt_templates")
    op.drop_table("generation_runtime_settings")
    op.drop_index("ix_idea_templates_active_order", table_name="idea_templates")
    op.drop_table("idea_templates")
    op.drop_index("ix_billing_plans_active_order", table_name="billing_plans")
    op.drop_table("billing_plans")
