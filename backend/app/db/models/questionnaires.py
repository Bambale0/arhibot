from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class QuestionnaireCatalogConfig(Base):
    __tablename__ = "questionnaire_catalog_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    catalog: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_texts: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class QuestionnaireApplication(Base):
    __tablename__ = "questionnaire_applications"
    __table_args__ = (
        UniqueConstraint("session_id", name="uq_questionnaire_applications_session_id"),
        Index("ix_questionnaire_applications_created_at", "created_at"),
        Index("ix_questionnaire_applications_project_id", "project_id"),
        Index("ix_questionnaire_applications_status_created", "status", "created_at"),
        Index(
            "ix_questionnaire_applications_telegram_delivery",
            "telegram_delivery_status",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    catalog_version: Mapped[str] = mapped_column(String(64), nullable=False)
    selected_objects: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    accepted_objects: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    answers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    scene_asset_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="new", server_default="new")
    telegram_delivery_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending"
    )
    telegram_delivery_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    telegram_delivery_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    telegram_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
