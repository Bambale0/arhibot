from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BillingPayment(Base):
    __tablename__ = "billing_payments"
    __table_args__ = (
        UniqueConstraint("yookassa_payment_id", name="uq_billing_payments_yookassa_id"),
        UniqueConstraint("idempotence_key", name="uq_billing_payments_idempotence_key"),
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
