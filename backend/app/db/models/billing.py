from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BillingSettings(Base):
    __tablename__ = "billing_settings"
    __table_args__ = (
        CheckConstraint("vat_code IS NULL OR (vat_code >= 1 AND vat_code <= 12)", name="ck_billing_settings_vat_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    receipts_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    vat_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_subject: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payment_mode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class BillingPayment(Base):
    __tablename__ = "billing_payments"
    __table_args__ = (
        UniqueConstraint("yookassa_payment_id", name="uq_billing_payments_yookassa_id"),
        UniqueConstraint("idempotence_key", name="uq_billing_payments_idempotence_key"),
        UniqueConstraint("refund_id", name="uq_billing_payments_refund_id"),
        UniqueConstraint("refund_idempotence_key", name="uq_billing_payments_refund_idempotence_key"),
        Index("ix_billing_payments_user_created", "user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    package_code: Mapped[str] = mapped_column(String(64), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB", server_default="RUB")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", server_default="pending")
    yookassa_payment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotence_key: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmation_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    receipt_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    refund_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    refund_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    refund_idempotence_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
