from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.architecture.enums import (
    ArchitectureCameraProfile,
    ArchitectureRenderBatchStatus,
    ArchitectureRenderStatus,
)


class ArchitectureRenderCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    camera_profile: ArchitectureCameraProfile = ArchitectureCameraProfile.HERO_CORNER


class ArchitectureRenderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    batch_id: UUID | None
    target_idea_id: UUID | None
    status: ArchitectureRenderStatus
    source_digest: str
    renderer_profile: str
    camera_profile: ArchitectureCameraProfile
    renderer_version: str | None
    output_asset_id: UUID | None
    image_url: str | None
    width: int | None
    height: int | None
    quality_score: float | None
    quality_report: dict[str, Any] | None
    selected_for_batch: bool
    error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class ArchitectureRenderBatchResponse(BaseModel):
    batch_id: UUID
    project_id: UUID
    target_idea_id: UUID | None
    status: ArchitectureRenderBatchStatus
    source_digest: str
    selected_render_id: UUID | None
    renders: list[ArchitectureRenderResponse]
