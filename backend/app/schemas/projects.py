from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.projects.enums import ProjectStatus


class ProjectContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    house_area_m2: float | None = Field(default=None, gt=0)
    floors: int | None = Field(default=None, ge=1, le=10)
    plot_area_m2: float | None = Field(default=None, gt=0)
    bedrooms: int | None = Field(default=None, ge=0, le=30)
    bathrooms: int | None = Field(default=None, ge=0, le=30)
    architecture_style: str | None = Field(default=None, max_length=80)


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Дом у озера",
                    "context": {"house_area_m2": 160, "floors": 2, "plot_area_m2": 1000},
                }
            ]
        }
    )

    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=3000)
    context: ProjectContext = Field(default_factory=ProjectContext)


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=3000)
    status: ProjectStatus | None = None
    context: ProjectContext | None = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    status: ProjectStatus
    context: ProjectContext
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    next_cursor: str | None = None
    has_more: bool = False
