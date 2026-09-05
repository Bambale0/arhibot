from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class TelegramContentUpdate(BaseModel):
    bot_name: str = Field(min_length=1, max_length=64)
    short_description: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=512)
    start_text: str = Field(min_length=1, max_length=4096)
    open_button_text: str = Field(min_length=1, max_length=64)
    start_command_description: str = Field(min_length=1, max_length=256)
    app_command_description: str = Field(min_length=1, max_length=256)

    @field_validator("*")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Telegram content fields must not be empty")
        return value


class TelegramContentResponse(BaseModel):
    configured: bool
    bot_name: str | None = None
    short_description: str | None = None
    description: str | None = None
    start_text: str | None = None
    open_button_text: str | None = None
    start_command_description: str | None = None
    app_command_description: str | None = None
    updated_at: datetime | None = None
