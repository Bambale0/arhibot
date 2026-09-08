from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.architecture.enums import ArchitectureRenderStatus


class ArchitectureRenderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    status: ArchitectureRenderStatus
    source_digest: str
    renderer_profile: str
    renderer_version: str | None
    image_url: str | None
    width: int | None
    height: int | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
