from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.architecture.schemas import ArchitecturePackage
from app.domain.generations.enums import GenerationType
from app.domain.users.enums import UserRole, UserStatus
from app.schemas.generations import GenerationResponse


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
    def validate_receipt_fields(self) -> BillingSettingsUpdate:
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


IdeaMediaKind = Literal["photo", "reference", "scheme"]


class IdeaMediaInput(BaseModel):
    asset_id: UUID
    kind: IdeaMediaKind
    label: str = Field(min_length=1, max_length=120)

    @field_validator("label")
    @classmethod
    def strip_label(cls, value: str) -> str:
        return value.strip()


class IdeaMediaResponse(BaseModel):
    asset_id: UUID
    kind: IdeaMediaKind
    label: str
    url: str


class IdeaCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    category: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=3000)
    generation_type: GenerationType
    prompt: str = Field(default="", max_length=5000)
    image_asset_id: UUID | None = None
    architecture_project_id: UUID | None = None
    media: list[IdeaMediaInput] = Field(default_factory=list, max_length=24)
    is_active: bool = True
    sort_order: int = Field(default=0, ge=-100_000, le=100_000)


class IdeaUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    category: str | None = Field(default=None, min_length=1, max_length=64)
    text: str | None = Field(default=None, min_length=1, max_length=3000)
    generation_type: GenerationType | None = None
    prompt: str | None = Field(default=None, max_length=5000)
    image_asset_id: UUID | None = None
    architecture_project_id: UUID | None = None
    media: list[IdeaMediaInput] | None = Field(default=None, max_length=24)
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
    architecture_project_id: UUID | None
    media: list[IdeaMediaResponse]
    architecture: ArchitecturePackage | None
    model_url: str | None
    model_original_filename: str | None
    model_size_bytes: int | None
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
    media: list[IdeaMediaResponse]
    architecture: ArchitecturePackage | None
    model_url: str | None


class IdeaAnswerSummary(BaseModel):
    question: str
    answer: str


class IdeaObjectSummary(BaseModel):
    key: str
    title: str
    answers: list[IdeaAnswerSummary]


class IdeaPublicationCreate(BaseModel):
    generation_id: UUID


class IdeaPublicationUpdate(BaseModel):
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=-100_000, le=100_000)


class PublicIdeaPublicationResponse(BaseModel):
    id: UUID
    title: str
    category: str
    generation_type: GenerationType
    image_url: str | None
    preview_url: str | None = None
    objects: list[IdeaObjectSummary]
    selected_objects: list[str]
    published_at: datetime
    is_saved: bool = False


class IdeaPublicationResponse(PublicIdeaPublicationResponse):
    generation_id: UUID
    owner_published: bool
    is_active: bool
    sort_order: int
    updated_at: datetime


class IdeaSaveResponse(BaseModel):
    idea_id: UUID
    is_saved: bool


class AdminAiSandboxCreate(BaseModel):
    model_name: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=8000)
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("model_name", "prompt")
    @classmethod
    def strip_sandbox_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @model_validator(mode="after")
    def protect_provider_fields(self) -> "AdminAiSandboxCreate":
        reserved = {"model_name", "prompt", "image_url", "image_urls"}
        conflict = reserved.intersection(self.params)
        if conflict:
            raise ValueError(
                f"Sandbox params cannot override provider fields: {', '.join(sorted(conflict))}"
            )
        return self


class AdminAiOrbitCreate(BaseModel):
    source_generation_id: UUID
    model_name: str = Field(min_length=1, max_length=120)
    prompt: str = Field(default="", max_length=2000)
    params: dict[str, Any] = Field(default_factory=dict)
    frame_count: int = Field(default=8, ge=6, le=12)
    frame_duration_ms: int = Field(default=180, ge=80, le=1000)

    @field_validator("model_name")
    @classmethod
    def strip_orbit_model(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("prompt")
    @classmethod
    def strip_orbit_prompt(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def protect_provider_fields(self) -> "AdminAiOrbitCreate":
        reserved = {"model_name", "prompt", "image_url", "image_urls"}
        conflict = reserved.intersection(self.params)
        if conflict:
            raise ValueError(
                f"Orbit params cannot override provider fields: {', '.join(sorted(conflict))}"
            )
        return self


class AdminAiFlyoverGifCreate(BaseModel):
    source_generation_id: UUID
    model_name: str = Field(min_length=1, max_length=120)
    prompt: str = Field(default="", max_length=2000)
    params: dict[str, Any] = Field(default_factory=dict)
    keyframe_count: int = Field(default=6, ge=4, le=8)
    inbetween_frames: int = Field(default=3, ge=0, le=5)
    frame_duration_ms: int = Field(default=120, ge=60, le=500)

    @field_validator("model_name")
    @classmethod
    def strip_flyover_model(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("prompt")
    @classmethod
    def strip_flyover_prompt(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def protect_provider_fields(self) -> "AdminAiFlyoverGifCreate":
        reserved = {"model_name", "prompt", "image_url", "image_urls"}
        conflict = reserved.intersection(self.params)
        if conflict:
            raise ValueError(
                f"Flyover params cannot override provider fields: {', '.join(sorted(conflict))}"
            )
        return self


class AdminAiHistoryItem(BaseModel):
    kind: Literal["sandbox", "orbit", "flyover_gif"]
    generation: GenerationResponse
    prompt: str
    params: dict[str, Any] = Field(default_factory=dict)
    frame_count: int | None = None
    frame_duration_ms: int | None = None
    keyframe_count: int | None = None
    inbetween_frames: int | None = None


class GenerationRuntimeUpdate(BaseModel):
    primary_model: str = Field(min_length=1, max_length=120)
    fallback_model: str | None = Field(default=None, max_length=120)
    primary_timeout_seconds: int = Field(default=90, ge=30, le=600)
    primary_params: dict[str, Any] = Field(default_factory=dict)
    fallback_params: dict[str, Any] = Field(default_factory=dict)
    mode_params: dict[str, dict[str, Any]] = Field(default_factory=dict)
    masked_edit_provider_context_margin_fraction: float | None = Field(default=None, ge=0, le=0.25)
    masked_edit_feather_fraction: float | None = Field(default=None, ge=0, le=0.1)
    masked_edit_feather_min_px: int | None = Field(default=None, ge=0, le=128)
    masked_edit_feather_max_px: int | None = Field(default=None, ge=1, le=256)
    masked_edit_recomposite_feather_multiplier: float | None = Field(default=None, ge=1, le=4)
    masked_edit_boundary_band_px: int | None = Field(default=None, ge=1, le=64)
    masked_edit_max_luma_excess: float | None = Field(default=None, ge=0, le=255)
    masked_edit_max_color_excess: float | None = Field(default=None, ge=0, le=442)
    masked_edit_max_straight_edge_fraction: float | None = Field(default=None, ge=0, le=1)
    generation_quality_max_retries: int | None = Field(default=None, ge=0, le=3)

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
    def validate_modes(self) -> GenerationRuntimeUpdate:
        allowed = {item.value for item in GenerationType}
        unknown = set(self.mode_params) - allowed
        if unknown:
            raise ValueError(f"Unknown generation modes: {', '.join(sorted(unknown))}")
        reserved = {"model_name", "prompt", "image_url", "image_urls"}
        groups = {
            "primary_params": self.primary_params,
            "fallback_params": self.fallback_params,
            **{f"mode_params.{key}": value for key, value in self.mode_params.items()},
        }
        for label, params in groups.items():
            conflict = reserved.intersection(params)
            if conflict:
                raise ValueError(
                    f"{label} cannot override provider fields: {', '.join(sorted(conflict))}"
                )
        if (
            self.masked_edit_feather_min_px is not None
            and self.masked_edit_feather_max_px is not None
            and self.masked_edit_feather_min_px > self.masked_edit_feather_max_px
        ):
            raise ValueError("masked edit feather min cannot exceed max")
        return self


class GenerationRuntimeResponse(BaseModel):
    primary_model: str | None = None
    fallback_model: str | None = None
    primary_timeout_seconds: int = 90
    primary_params: dict[str, Any] = Field(default_factory=dict)
    fallback_params: dict[str, Any] = Field(default_factory=dict)
    mode_params: dict[str, dict[str, Any]] = Field(default_factory=dict)
    masked_edit_provider_context_margin_fraction: float
    masked_edit_feather_fraction: float
    masked_edit_feather_min_px: int
    masked_edit_feather_max_px: int
    masked_edit_recomposite_feather_multiplier: float
    masked_edit_boundary_band_px: int
    masked_edit_max_luma_excess: float
    masked_edit_max_color_excess: float
    masked_edit_max_straight_edge_fraction: float
    generation_quality_max_retries: int
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

    @field_validator("template")
    @classmethod
    def require_user_prompt_placeholder(cls, value: str) -> str:
        value = value.strip()
        if "{user_prompt}" not in value:
            raise ValueError("Generation prompt template must contain {user_prompt}.")
        return value


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


class AdminPaymentReconcile(BaseModel):
    provider_payment_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


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
    auth_rate_limit_per_minute: int = Field(default=30, ge=1, le=100_000)
    generation_rate_limit_per_minute: int = Field(default=10, ge=1, le=100_000)
    payment_rate_limit_per_minute: int = Field(default=10, ge=1, le=100_000)
    registration_rate_limit_per_day: int = Field(default=20, ge=1, le=100_000)
    yookassa_webhook_rate_limit_per_minute: int = Field(default=120, ge=1, le=100_000)
    asset_upload_rate_limit_per_minute: int = Field(default=12, ge=1, le=100_000)
    asset_max_retained_count_per_user: int = Field(default=200, ge=1, le=100_000)
    asset_max_retained_bytes_per_user: int = Field(
        default=512 * 1024 * 1024,
        ge=1,
        le=10_000_000_000_000,
    )
    generation_max_inflight_per_user: int = Field(default=2, ge=1, le=1000)
    initial_concept_offer_limit_per_day: int = Field(default=3, ge=1, le=1000)
    starter_credits: int = Field(default=0, ge=0, le=1_000_000)
    initial_concept_credits: int = Field(default=0, ge=0, le=1_000_000)
    media_retention_days: int = Field(default=30, ge=1, le=3650)
    backup_interval_hours: int = Field(default=24, ge=1, le=8760)
    backup_retention_days: int = Field(default=14, ge=1, le=3650)
    media_min_free_bytes: int = Field(
        default=2 * 1024 * 1024 * 1024,
        ge=64 * 1024 * 1024,
        le=10_000_000_000_000,
    )


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
