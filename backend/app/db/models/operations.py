from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OperationalSettings(Base):
    __tablename__ = "operational_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    auth_rate_limit_per_minute: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="30"
    )
    generation_rate_limit_per_minute: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="10"
    )
    payment_rate_limit_per_minute: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="10"
    )
    registration_rate_limit_per_day: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="20"
    )
    yookassa_webhook_rate_limit_per_minute: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="120"
    )
    asset_upload_rate_limit_per_minute: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="12"
    )
    asset_max_retained_count_per_user: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="200"
    )
    asset_max_retained_bytes_per_user: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=str(512 * 1024 * 1024)
    )
    generation_max_inflight_per_user: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="2"
    )
    initial_concept_offer_limit_per_day: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="3"
    )
    starter_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    initial_concept_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    media_retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    backup_interval_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    backup_retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
