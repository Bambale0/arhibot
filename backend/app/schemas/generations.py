from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.generations.enums import GenerationStatus, GenerationType
from app.schemas.assets import AssetResponse


class GenerationCreate(BaseModel):
    project_id: UUID
    input_asset_id: UUID
    type: GenerationType
    prompt: str = Field(default="", max_length=4000)


class GenerationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    input_asset_id: UUID
    output_asset: AssetResponse | None = None
    type: GenerationType
    status: GenerationStatus
    prompt: str
    model_name: str | None = None
    fallback_used: bool = False
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class GenerationListResponse(BaseModel):
    items: list[GenerationResponse]
