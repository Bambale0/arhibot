from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "local"
    app_name: str = "AuRoom API"
    app_version: str = "0.6.0"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/app"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: str = "http://localhost:3000"

    jwt_secret: str = "local-only-change-me-access-secret-32-bytes"
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_issuer: str = "ai-architecture-platform"
    jwt_audience: str = "ai-architecture-api"
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 2_592_000
    refresh_token_secret: str = "local-only-change-me-refresh-secret-32-bytes"

    telegram_bot_token: str | None = None
    telegram_webapp_url: str | None = None
    telegram_init_data_ttl_seconds: int = 3600

    # Provider credentials/infrastructure only. Model selection and model params live in DB/admin.
    nexus_api_key: str | None = None
    nexus_base_url: str = "https://nexusapi.dev"
    nexus_task_timeout_seconds: int = 180
    nexus_poll_interval_seconds: float = 2.0

    # YooKassa credentials/infrastructure only. Tariffs live in DB/admin.
    yookassa_shop_id: str | None = None
    yookassa_secret_key: str | None = None
    yookassa_base_url: str = "https://api.yookassa.ru/v3"
    yookassa_return_url: str | None = None

    media_root: str = "/data/media"
    media_public_base_url: str = "http://localhost:8000"
    max_image_size_bytes: int = 20 * 1024 * 1024
    max_image_pixels: int = 80_000_000

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        if self.access_token_ttl_seconds < 60:
            raise ValueError("ACCESS_TOKEN_TTL_SECONDS must be at least 60")
        if self.refresh_token_ttl_seconds <= self.access_token_ttl_seconds:
            raise ValueError("REFRESH_TOKEN_TTL_SECONDS must exceed access-token TTL")
        if self.telegram_init_data_ttl_seconds < 60:
            raise ValueError("TELEGRAM_INIT_DATA_TTL_SECONDS must be at least 60")
        if self.max_image_size_bytes < 1_048_576:
            raise ValueError("MAX_IMAGE_SIZE_BYTES must be at least 1 MiB")
        if self.max_image_pixels < 1_000_000:
            raise ValueError("MAX_IMAGE_PIXELS must be at least 1,000,000")
        if self.nexus_task_timeout_seconds < 30:
            raise ValueError("NEXUS_TASK_TIMEOUT_SECONDS must be at least 30")
        if self.nexus_poll_interval_seconds < 0.5:
            raise ValueError("NEXUS_POLL_INTERVAL_SECONDS must be at least 0.5")
        if self.is_production:
            insecure = {
                "local-only-change-me-access-secret-32-bytes",
                "local-only-change-me-refresh-secret-32-bytes",
            }
            if self.jwt_secret in insecure or self.refresh_token_secret in insecure:
                raise ValueError("Production JWT/refresh secrets must be explicitly configured")
            if len(self.jwt_secret) < 32 or len(self.refresh_token_secret) < 32:
                raise ValueError("Production JWT/refresh secrets must be at least 32 characters")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
