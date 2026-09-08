from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.architecture.enums import ArchitectureCameraProfile, ArchitectureRenderStatus


class ArchitectureRenderCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    camera_profile: ArchitectureCameraProfile = ArchitectureCameraProfile.HERO_CORNER


class ArchitectureRenderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    status: ArchitectureRenderStatus
    source_digest: str
    renderer_profile: str
    camera_profile: ArchitectureCameraProfile
    renderer_version: str | None
    image_url: str | None
    width: int | None
    height: int | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
