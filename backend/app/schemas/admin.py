from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.generations.enums import GenerationType
from app.domain.users.enums import UserRole, UserStatus


class AdminOverviewResponse(BaseModel):
    yookassa_configured: bool
    nexus_configured: bool
    telegram_configured: bool


class BillingPlanCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    credits: int = Field(gt=0, le=1_000_000)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="RUB", min_length=3, max_length=3)
    is_active: bool = True
    sort_order: int = Field(default=0, ge=-100_000, le=100_000)

    @field_validator("code", "name")
    @classmethod
    def strip_required(cls, value: str) -> str:
        return value.strip()

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()


class BillingPlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    credits: int | None = Field(default=None, gt=0, le=1_000_000)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=-100_000, le=100_000)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None


class BillingPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    description: str | None
    credits: int
    amount: Decimal
    currency: str
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


class BillingSettingsUpdate(BaseModel):
    receipts_enabled: bool = False
    vat_code: int | None = Field(default=None, ge=1, le=12)
    payment_subject: str | None = Field(default=None, max_length=64)
    payment_mode: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_receipt_fields(self) -> "BillingSettingsUpdate":
        if self.receipts_enabled and (
            self.vat_code is None
            or not (self.payment_subject or "").strip()
            or not (self.payment_mode or "").strip()
        ):
            raise ValueError("VAT code, payment subject and payment mode are required for receipts")
        return self


class BillingSettingsResponse(BaseModel):
    receipts_enabled: bool
    vat_code: int | None
    payment_subject: str | None
    payment_mode: str | None
    updated_at: datetime | None = None


class IdeaCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    category: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=3000)
    generation_type: GenerationType
    prompt: str = Field(default="", max_length=5000)
    image_asset_id: UUID | None = None
    is_active: bool = True
    sort_order: int = Field(default=0, ge=-100_000, le=100_000)


class IdeaUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    category: str | None = Field(default=None, min_length=1, max_length=64)
    text: str | None = Field(default=None, min_length=1, max_length=3000)
    generation_type: GenerationType | None = None
    prompt: str | None = Field(default=None, max_length=5000)
    image_asset_id: UUID | None = None
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=-100_000, le=100_000)


class IdeaResponse(BaseModel):
    id: UUID
    title: str
    category: str
    text: str
    generation_type: GenerationType
    prompt: str
    image_asset_id: UUID | None
    image_url: str | None
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


class PublicIdeaResponse(BaseModel):
    id: UUID
    title: str
    category: str
    text: str
    generation_type: GenerationType
    prompt: str
    image_url: str | None


class GenerationRuntimeUpdate(BaseModel):
    primary_model: str = Field(min_length=1, max_length=120)
    fallback_model: str | None = Field(default=None, max_length=120)
    primary_params: dict[str, Any] = Field(default_factory=dict)
    fallback_params: dict[str, Any] = Field(default_factory=dict)
    mode_params: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @field_validator("primary_model")
    @classmethod
    def strip_primary(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Primary model is required")
        return value

    @field_validator("fallback_model")
    @classmethod
    def strip_fallback(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def validate_modes(self) -> "GenerationRuntimeUpdate":
        allowed = {item.value for item in GenerationType}
        unknown = set(self.mode_params) - allowed
        if unknown:
            raise ValueError(f"Unknown generation modes: {', '.join(sorted(unknown))}")
        return self


class GenerationRuntimeResponse(BaseModel):
    primary_model: str | None = None
    fallback_model: str | None = None
    primary_params: dict[str, Any] = Field(default_factory=dict)
    fallback_params: dict[str, Any] = Field(default_factory=dict)
    mode_params: dict[str, dict[str, Any]] = Field(default_factory=dict)
    updated_at: datetime | None = None


class GenerationPriceUpdate(BaseModel):
    credits: int = Field(gt=0, le=1_000_000)
    is_active: bool = True


class GenerationPriceResponse(BaseModel):
    generation_type: GenerationType
    credits: int
    is_active: bool
    updated_at: datetime


class PromptTemplateUpdate(BaseModel):
    template: str = Field(min_length=1, max_length=20_000)


class PromptTemplateResponse(BaseModel):
    generation_type: GenerationType
    template: str
    updated_at: datetime


class AdminUserResponse(BaseModel):
    id: UUID
    display_name: str
    status: UserStatus
    role: UserRole
    credits_balance: int
    created_at: datetime
    updated_at: datetime


class CreditAdjustmentRequest(BaseModel):
    delta: int = Field(ge=-1_000_000, le=1_000_000)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("delta")
    @classmethod
    def non_zero_delta(cls, value: int) -> int:
        if value == 0:
            raise ValueError("Credit delta must not be zero")
        return value


class CreditTransactionResponse(BaseModel):
    id: UUID
    user_id: UUID
    amount: int
    balance_after: int
    kind: str
    reference_type: str | None
    reference_id: str | None
    reason: str | None
    actor_user_id: UUID | None
    created_at: datetime


class UserStateUpdate(BaseModel):
    status: UserStatus | None = None
    role: UserRole | None = None


class AdminPaymentResponse(BaseModel):
    id: UUID
    user_id: UUID
    package_code: str
    credits: int
    amount: Decimal
    currency: str
    status: str
    yookassa_payment_id: str | None
    receipt_email: str | None
    refund_id: str | None
    refund_status: str | None
    provider_error: str | None
    created_at: datetime
    updated_at: datetime
    paid_at: datetime | None
    refunded_at: datetime | None


BroadcastSegment = Literal["all", "with_credits", "without_credits"]


class BroadcastCreate(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    segment: BroadcastSegment = "all"
    scheduled_at: datetime | None = None


class BroadcastResponse(BaseModel):
    id: UUID
    text: str
    status: str
    segment: BroadcastSegment
    recipient_count: int
    sent_count: int
    failed_count: int
    scheduled_at: datetime | None
    canceled_at: datetime | None
    created_at: datetime
    updated_at: datetime
    sent_at: datetime | None


class OperationalSettingsUpdate(BaseModel):
    auth_rate_limit_per_minute: int | None = Field(default=None, ge=1, le=100_000)
    generation_rate_limit_per_minute: int | None = Field(default=None, ge=1, le=100_000)
    payment_rate_limit_per_minute: int | None = Field(default=None, ge=1, le=100_000)
    media_retention_days: int | None = Field(default=None, ge=1, le=3650)
    backup_retention_days: int | None = Field(default=None, ge=1, le=3650)


class OperationalSettingsResponse(OperationalSettingsUpdate):
    updated_at: datetime | None = None


class AuditLogResponse(BaseModel):
    id: UUID
    actor_user_id: UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    details: dict[str, Any]
    created_at: datetime
