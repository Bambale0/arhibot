from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.architecture.enums import ArchitectureRenderStatus


class ArchitectureRender(Base):
    __tablename__ = "architecture_renders"
    __table_args__ = (
        Index("ix_architecture_renders_user_created", "user_id", "created_at"),
        Index("ix_architecture_renders_project_created", "project_id", "created_at"),
        Index("ix_architecture_renders_status_created", "status", "created_at"),
        Index("ix_architecture_renders_batch_created", "batch_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    batch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    target_idea_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("idea_templates.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[ArchitectureRenderStatus] = mapped_column(
        Enum(
            ArchitectureRenderStatus,
            name="architecture_render_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=ArchitectureRenderStatus.QUEUED,
        server_default=ArchitectureRenderStatus.QUEUED.value,
    )
    architecture: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    renderer_profile: Mapped[str] = mapped_column(
        String(80), nullable=False, default="blender_eevee_v1", server_default="blender_eevee_v1"
    )
    camera_profile: Mapped[str] = mapped_column(
        String(40), nullable=False, default="hero_corner", server_default="hero_corner"
    )
    renderer_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True, unique=True)
    output_asset_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_report: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    selected_for_batch: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
