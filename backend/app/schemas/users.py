from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.users.enums import UserStatus


class UserCapabilities(BaseModel):
    can_generate: bool = True


class CurrentUserResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "baf8f2bb-3ca0-45d0-89a7-b9e858c15ad8",
                    "display_name": "Игорь",
                    "avatar_url": None,
                    "status": "active",
                    "created_at": "2026-09-03T11:40:32Z",
                    "updated_at": "2026-09-03T11:40:32Z",
                    "capabilities": {"can_generate": True},
                }
            ]
        },
    )

    id: UUID
    display_name: str
    avatar_url: str | None = None
    status: UserStatus
    created_at: datetime
    updated_at: datetime
    capabilities: UserCapabilities = Field(default_factory=UserCapabilities)


class UpdateCurrentUserRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"display_name": "Игорь"}]})

    display_name: str = Field(min_length=1, max_length=120)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Display name must not be blank")
        return value
