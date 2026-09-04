from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.assets.enums import AssetPurpose, AssetType


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        Index("ix_assets_user_created", "user_id", "created_at"),
        Index("ix_assets_project_id", "project_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[AssetType] = mapped_column(
        Enum(AssetType, name="asset_type", values_callable=lambda enum: [item.value for item in enum]),
        nullable=False,
        default=AssetType.IMAGE,
        server_default=AssetType.IMAGE.value,
    )
    purpose: Mapped[AssetPurpose] = mapped_column(
        Enum(
            AssetPurpose,
            name="asset_purpose",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
