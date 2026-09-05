from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TelegramContentSettings(Base):
    __tablename__ = "telegram_content_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    short_description: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    open_button_text: Mapped[str | None] = mapped_column(String(64), nullable=True)
    start_command_description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    app_command_description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
