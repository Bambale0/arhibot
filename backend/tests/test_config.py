import pytest

from app.core.config import Settings


def test_cors_origins_can_be_comma_separated() -> None:
    settings = Settings(cors_origins="https://example.com,https://admin.example.com")
    assert settings.cors_origin_list == ["https://example.com", "https://admin.example.com"]


def test_default_secrets_are_rejected_in_production() -> None:
    with pytest.raises(ValueError, match="Production JWT/refresh secrets"):
        Settings(app_env="production")
