import pytest

from app.core.config import Settings


def test_primary_nexus_timeout_defaults_to_fast_failover_budget() -> None:
    settings = Settings(
        jwt_secret="x" * 32,
        refresh_token_secret="y" * 32,
    )

    assert settings.nexus_task_timeout_seconds == 180
    assert settings.nexus_primary_timeout_seconds == 90


def test_primary_nexus_timeout_cannot_exceed_provider_timeout() -> None:
    with pytest.raises(ValueError, match="NEXUS_PRIMARY_TIMEOUT_SECONDS"):
        Settings(
            jwt_secret="x" * 32,
            refresh_token_secret="y" * 32,
            nexus_task_timeout_seconds=60,
            nexus_primary_timeout_seconds=90,
        )
