from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.users import CurrentUserResponse


class RegisterRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "email": "igor@example.com",
                    "password": "correct-horse-battery-staple",
                    "display_name": "Игорь",
                }
            ]
        }
    )

    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Display name must not be blank")
        return value


class LoginRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"email": "igor@example.com", "password": "correct-horse-battery-staple"}
            ]
        }
    )

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TelegramAuthRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"init_data": "query_id=...&user=...&auth_date=...&hash=..."}]
        }
    )

    init_data: str = Field(min_length=1, max_length=16384)


class RefreshTokenRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"refresh_token": "opaque-refresh-token"}]}
    )

    refresh_token: str = Field(min_length=32, max_length=512)


class TokenPairResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "access_token": "eyJ...",
                    "refresh_token": "jBX...",
                    "token_type": "bearer",
                    "expires_in": 900,
                    "user": {
                        "id": "baf8f2bb-3ca0-45d0-89a7-b9e858c15ad8",
                        "display_name": "Игорь",
                        "avatar_url": None,
                        "status": "active",
                        "created_at": "2026-09-03T11:40:32Z",
                        "updated_at": "2026-09-03T11:40:32Z",
                        "capabilities": {"can_generate": True},
                    },
                }
            ]
        }
    )

    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: CurrentUserResponse


class LogoutResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"success": True}]})

    success: Literal[True] = True
