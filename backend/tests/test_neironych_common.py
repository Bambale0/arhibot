from __future__ import annotations

import httpx
import pytest

from app.core.config import Settings
from app.providers.neironych import (
    NeironychProviderError,
    build_neironych_http_config,
    extract_request_id,
    safe_error,
)


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "test",
        "neironych_api_key": "secret-test-key",
        "neironych_api_base_url": "https://api.neironych.example",
        "neironych_request_timeout_seconds": 180,
        "neironych_http_connect_timeout_seconds": 5,
    }
    values.update(overrides)
    return Settings(**values)


def test_neironych_http_config_uses_bearer_auth_and_origin() -> None:
    config = build_neironych_http_config(_settings())

    assert config.base_url == "https://api.neironych.example"
    assert config.headers == {
        "Authorization": "Bearer secret-test-key",
        "Content-Type": "application/json",
    }
    assert config.timeout.connect == 5
    assert config.timeout.read == 180


def test_neironych_http_config_requires_key() -> None:
    with pytest.raises(NeironychProviderError, match="NEIRONYCH_API_KEY"):
        build_neironych_http_config(_settings(neironych_api_key=""))


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"x-request-id": "req-1"}, "req-1"),
        ({"request-id": "req-2"}, "req-2"),
        ({"x-correlation-id": "req-3"}, "req-3"),
        ({}, None),
    ],
)
def test_extract_request_id(headers: dict[str, str], expected: str | None) -> None:
    response = httpx.Response(200, headers=headers)
    assert extract_request_id(response) == expected


def test_safe_error_prefers_small_provider_message_without_dumping_payload() -> None:
    response = httpx.Response(
        400,
        json={
            "error": {"message": "invalid model"},
            "debug": "must-not-leak",
        },
    )

    assert safe_error(response) == "invalid model"


def test_safe_error_handles_non_json_response() -> None:
    response = httpx.Response(502, text="upstream unavailable")
    assert safe_error(response) == "upstream unavailable"
