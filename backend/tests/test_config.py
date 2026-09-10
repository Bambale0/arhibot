import pytest

from app.core.config import Settings


def test_cors_origins_can_be_comma_separated() -> None:
    settings = Settings(cors_origins="https://example.com,https://admin.example.com")
    assert settings.cors_origin_list == ["https://example.com", "https://admin.example.com"]


def test_default_secrets_are_rejected_in_production() -> None:
    with pytest.raises(ValueError, match="Production JWT/refresh secrets"):
        Settings(app_env="production")


def test_production_auth_secrets_must_be_distinct() -> None:
    secret = "same-production-secret-that-is-at-least-32-characters"
    with pytest.raises(ValueError, match="must be different"):
        Settings(
            app_env="production",
            jwt_secret=secret,
            refresh_token_secret=secret,
            media_signing_secret="independent-media-secret-at-least-32-chars",
        )


def test_production_requires_independent_media_signing_secret() -> None:
    with pytest.raises(ValueError, match="media signing secret"):
        Settings(
            app_env="production",
            jwt_secret="access-production-secret-at-least-32-characters",
            refresh_token_secret="refresh-production-secret-at-least-32-characters",
        )


def test_redis_timeouts_must_be_positive() -> None:
    with pytest.raises(ValueError, match="Redis socket timeouts"):
        Settings(redis_socket_timeout_seconds=0)


def test_media_url_ttl_is_bounded() -> None:
    with pytest.raises(ValueError, match="MEDIA_URL_TTL_SECONDS"):
        Settings(media_url_ttl_seconds=30)
