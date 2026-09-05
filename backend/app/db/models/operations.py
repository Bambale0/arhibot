from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OperationalSettings(Base):
    __tablename__ = "operational_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    auth_rate_limit_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generation_rate_limit_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_rate_limit_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    media_retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    backup_interval_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    backup_retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
