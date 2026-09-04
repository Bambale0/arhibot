from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.assets.enums import AssetPurpose, AssetType


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID | None
    type: AssetType
    purpose: AssetPurpose
    original_filename: str | None
    mime_type: str
    size_bytes: int
    width: int
    height: int
    url: str
    created_at: datetime
