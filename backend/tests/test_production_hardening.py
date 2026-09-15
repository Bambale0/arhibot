from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from PIL import Image
from fastapi import Response
from starlette.requests import Request

from app.api.v1 import auth as auth_api
from app.api.v1.billing import _read_limited_body
from app.core.config import Settings
from app.core.errors import AppError
from app.providers.yookassa import YooKassaProvider
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services import asset_service as asset_service_module
from app.services.asset_service import LocalMediaStorage
from app.services.billing_service import BillingService
from app.workers import generation_worker
from app.workers.generation_worker import (
    _commit_output_or_cleanup,
    _validate_connected_peer,
    _validate_remote_image_url,
)


def _request(ip: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [(b"x-real-ip", ip.encode())],
            "client": (ip, 12345),
            "server": ("test", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )


@pytest.mark.asyncio
async def test_email_auth_rate_limits_source_and_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple] = []

    class FakeLimiter:
        def __init__(self, session) -> None:  # noqa: ANN001, ARG002
            pass

        async def enforce(self, kind: str, identity: str) -> None:
            calls.append(("enforce", kind, identity))

        async def enforce_registration_daily(self, identity: str) -> None:
            calls.append(("registration-daily", identity))

    class FakeAuth:
        async def register(self, email: str, password: str, display_name: str):  # noqa: ANN001
            return SimpleNamespace(refresh_token="r" * 64)

        async def login(self, email: str, password: str):  # noqa: ANN001
            return SimpleNamespace(refresh_token="r" * 64)

    monkeypatch.setattr(auth_api, "RateLimitService", FakeLimiter)
    monkeypatch.setattr(auth_api, "_service", lambda session, settings: FakeAuth())

    settings = Settings()
    response = Response()
    await auth_api.register_user(
        RegisterRequest(
            email="User@Example.com",
            password="correct-horse-battery-staple",
            display_name="User",
        ),
        _request("203.0.113.10"),
        response,
        object(),  # type: ignore[arg-type]
        settings,
    )
    assert ("enforce", "auth", "register-ip:203.0.113.10") in calls
    assert ("enforce", "auth", "register-email:user@example.com") in calls
    assert ("registration-daily", "203.0.113.10") in calls

    calls.clear()
    await auth_api.login_user(
        LoginRequest(
            email="User@Example.com",
            password="correct-horse-battery-staple",
        ),
        _request("203.0.113.10"),
        Response(),
        object(),  # type: ignore[arg-type]
        settings,
    )
    assert ("enforce", "auth", "login-ip:203.0.113.10") in calls
    assert ("enforce", "auth", "login-email:user@example.com") in calls


@pytest.mark.asyncio
async def test_yookassa_webhook_body_stops_at_configured_limit() -> None:
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {
            "type": "http.request",
            "body": b"x" * 65,
            "more_body": False,
        }

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/billing/webhooks/yookassa",
            "headers": [(b"content-type", b"application/json")],
            "client": ("203.0.113.20", 12345),
            "server": ("test", 80),
            "scheme": "http",
            "query_string": b"",
        },
        receive=receive,
    )
    with pytest.raises(AppError) as exc:
        await _read_limited_body(request, max_bytes=64)
    assert exc.value.status == 413


@pytest.mark.asyncio
async def test_unknown_yookassa_webhook_id_does_not_trigger_provider_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = BillingService(
        object(),  # type: ignore[arg-type]
        Settings(yookassa_shop_id="shop", yookassa_secret_key="secret"),
    )

    class FakeRepository:
        async def has_provider_payment(self, provider_id: str) -> bool:
            assert provider_id == "unknown-payment"
            return False

    service.repository = FakeRepository()  # type: ignore[assignment]
    provider_called = False

    async def unexpected_get_payment(self, provider_id: str):  # noqa: ANN001, ARG001
        nonlocal provider_called
        provider_called = True
        raise AssertionError("provider must not be called for unknown ids")

    monkeypatch.setattr(YooKassaProvider, "get_payment", unexpected_get_payment)

    with pytest.raises(AppError) as exc:
        await service.handle_webhook(
            {
                "event": "payment.succeeded",
                "object": {"id": "unknown-payment"},
            }
        )
    assert exc.value.status == 503
    assert exc.value.type == "billing_webhook_object_not_ready"
    assert provider_called is False


@pytest.mark.asyncio
async def test_generated_media_url_rejects_private_network_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(RuntimeError, match="non-public"):
        await _validate_remote_image_url("https://127.0.0.1/result.png")
    with pytest.raises(RuntimeError, match="credentials"):
        await _validate_remote_image_url("https://user:secret@example.com/result.png")
    with pytest.raises(RuntimeError, match="standard HTTPS port"):
        await _validate_remote_image_url("https://example.com:8443/result.png")

    def private_dns(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
        return [(2, 1, 6, "", ("10.1.2.3", 443))]

    monkeypatch.setattr(generation_worker.socket, "getaddrinfo", private_dns)
    with pytest.raises(RuntimeError, match="non-public"):
        await _validate_remote_image_url("https://cdn.example.test/result.png")


@pytest.mark.asyncio
async def test_generated_media_url_accepts_public_https_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def public_dns(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr(generation_worker.socket, "getaddrinfo", public_dns)
    url = "https://cdn.example.test/result.png"
    assert await _validate_remote_image_url(url) == url


def test_generated_media_connection_rejects_private_actual_peer() -> None:
    class FakeStream:
        def get_extra_info(self, name: str):
            assert name == "server_addr"
            return ("169.254.169.254", 443)

    response = SimpleNamespace(extensions={"network_stream": FakeStream()})
    with pytest.raises(RuntimeError, match="non-public"):
        _validate_connected_peer(response)  # type: ignore[arg-type]


def test_generated_media_connection_accepts_public_actual_peer() -> None:
    class FakeStream:
        def get_extra_info(self, name: str):
            assert name == "server_addr"
            return ("93.184.216.34", 443)

    response = SimpleNamespace(extensions={"network_stream": FakeStream()})
    _validate_connected_peer(response)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_ideas_feed_preview_is_webp_and_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "users" / "test" / "large.png"
    source.parent.mkdir(parents=True)
    Image.new("RGB", (2752, 1536), (120, 130, 140)).save(source, format="PNG")

    storage = LocalMediaStorage(
        Settings(
            media_root=str(tmp_path),
            media_public_base_url="https://app.example.test",
            media_signing_secret="preview-signing-secret-that-is-long-enough-001",
        )
    )
    preview = await storage.ensure_feed_preview("users/test/large.png")
    assert preview.is_file()
    with Image.open(preview) as image:
        assert image.format == "WEBP"
        assert max(image.size) <= 1280

    monkeypatch.setattr(asset_service_module.time, "time", lambda: 1_700_000_001)
    first = storage.signed_feed_preview_url("users/test/large.png")
    monkeypatch.setattr(asset_service_module.time, "time", lambda: 1_700_000_100)
    second = storage.signed_feed_preview_url("users/test/large.png")
    assert first == second
    parsed = urlsplit(first)
    query = parse_qs(parsed.query)
    expires = int(query["expires"][0])
    signature = query["signature"][0]
    assert query["preview"] == ["feed"]
    assert storage.verify_signature(
        "users/test/large.png",
        expires=expires,
        signature=signature,
        variant="feed",
    )
    assert not storage.verify_signature(
        "users/test/large.png",
        expires=expires,
        signature=signature,
    )


@pytest.mark.asyncio
async def test_generation_output_is_removed_if_database_commit_fails(
    tmp_path: Path,
) -> None:
    storage = LocalMediaStorage(
        Settings(
            media_root=str(tmp_path),
            media_public_base_url="http://test",
        )
    )
    relative_path = "users/test/orphan.png"
    await storage.write(relative_path, b"orphan")
    target = storage.absolute_path(relative_path)
    assert target.exists()

    class FailingSession:
        rolled_back = False

        async def commit(self) -> None:
            raise RuntimeError("database commit failed")

        async def rollback(self) -> None:
            self.rolled_back = True

    session = FailingSession()
    with pytest.raises(RuntimeError, match="database commit failed"):
        await _commit_output_or_cleanup(  # type: ignore[arg-type]
            session,
            storage,
            relative_path,
        )

    assert session.rolled_back is True
    assert target.exists() is False
