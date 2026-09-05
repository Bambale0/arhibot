from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class BillingPackageResponse(BaseModel):
    code: str
    label: str
    credits: int
    amount: Decimal
    currency: str = "RUB"


class BillingPaymentCreate(BaseModel):
    package_code: str = Field(min_length=1, max_length=64)
    receipt_email: EmailStr | None = None


class BillingPaymentResponse(BaseModel):
    id: UUID
    package_code: str
    credits: int
    amount: Decimal
    currency: str
    status: str
    confirmation_url: str | None = None
    receipt_email: str | None = None
    refund_status: str | None = None
    created_at: datetime
    paid_at: datetime | None = None
    refunded_at: datetime | None = None


class BillingSummaryResponse(BaseModel):
    enabled: bool
    receipt_required: bool
    credits_balance: int
    packages: list[BillingPackageResponse]
    payments: list[BillingPaymentResponse]
