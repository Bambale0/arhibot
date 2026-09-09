from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.generations.enums import GenerationStatus, GenerationType
from app.schemas.assets import AssetResponse


class NormalizedRect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def stay_inside_image(self) -> "NormalizedRect":
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("Normalized edit region must stay inside the image.")
        return self


class GenerationCreate(BaseModel):
    project_id: UUID
    input_asset_id: UUID | None = None
    type: GenerationType
    prompt: str = Field(default="", max_length=4000)
    composition_mode: Literal["replace", "masked_edit"] = "replace"
    edit_region: NormalizedRect | None = None
    protected_regions: list[NormalizedRect] = Field(default_factory=list, max_length=26)

    @model_validator(mode="after")
    def validate_composition(self) -> "GenerationCreate":
        if self.composition_mode == "masked_edit":
            if self.input_asset_id is None:
                raise ValueError("Masked edit requires an input image.")
            if self.edit_region is None:
                raise ValueError("Masked edit requires an edit region.")
        elif self.edit_region is not None or self.protected_regions:
            raise ValueError("Edit/protected regions require masked_edit composition mode.")
        return self


class GenerationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    input_asset_id: UUID | None
    output_asset: AssetResponse | None = None
    type: GenerationType
    status: GenerationStatus
    prompt: str
    credits_charged: int = 0
    model_name: str | None = None
    fallback_used: bool = False
    composition_mode: str = "replace"
    edit_region: NormalizedRect | None = None
    protected_regions: list[NormalizedRect] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class GenerationListResponse(BaseModel):
    items: list[GenerationResponse]
    next_cursor: str | None = None
    has_more: bool = False
