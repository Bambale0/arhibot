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


def _has_editable_area(edit: NormalizedRect, protected: list[NormalizedRect]) -> bool:
    clips: list[tuple[float, float, float, float]] = []
    edit_right = edit.x + edit.width
    edit_bottom = edit.y + edit.height
    for region in protected:
        left = max(edit.x, region.x)
        top = max(edit.y, region.y)
        right = min(edit_right, region.x + region.width)
        bottom = min(edit_bottom, region.y + region.height)
        if right > left and bottom > top:
            clips.append((left, top, right, bottom))
    if not clips:
        return True

    xs = sorted({edit.x, edit_right, *(value for clip in clips for value in (clip[0], clip[2]))})
    covered = 0.0
    for left, right in zip(xs, xs[1:], strict=False):
        if right <= left:
            continue
        middle = (left + right) / 2
        intervals = sorted(
            (top, bottom)
            for clip_left, top, clip_right, bottom in clips
            if clip_left <= middle < clip_right
        )
        merged = 0.0
        current_top: float | None = None
        current_bottom: float | None = None
        for top, bottom in intervals:
            if current_top is None:
                current_top, current_bottom = top, bottom
            elif top <= (current_bottom or top):
                current_bottom = max(current_bottom or bottom, bottom)
            else:
                merged += (current_bottom or current_top) - current_top
                current_top, current_bottom = top, bottom
        if current_top is not None:
            merged += (current_bottom or current_top) - current_top
        covered += (right - left) * merged

    return edit.width * edit.height - covered > 1e-9


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
            if not _has_editable_area(self.edit_region, self.protected_regions):
                raise ValueError("Masked edit region is fully covered by protected regions.")
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
