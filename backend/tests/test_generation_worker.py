import socket

import pytest

from app.core.config import Settings
from app.providers.nexus import NexusOutcomeUnknown
from app.workers.generation_worker import _download_image, _validate_remote_image_url


@pytest.mark.asyncio
async def test_generated_image_download_requires_https() -> None:
    settings = Settings(
        jwt_secret="x" * 32,
        refresh_token_secret="y" * 32,
    )
    with pytest.raises(RuntimeError, match="must use HTTPS"):
        await _download_image("http://cdn.example.test/output.png", settings)


@pytest.mark.asyncio
async def test_temporary_download_dns_error_preserves_provider_outcome(monkeypatch):
    def resolve(*args, **kwargs):
        raise socket.gaierror(socket.EAI_AGAIN, "Temporary failure in name resolution")

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    with pytest.raises(NexusOutcomeUnknown, match="temporarily"):
        await _download_image("https://cdn.example.test/output.png", Settings())


@pytest.mark.asyncio
async def test_permanent_download_dns_error_is_not_pending_recovery(monkeypatch):
    def resolve(*args, **kwargs):
        raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    with pytest.raises(RuntimeError, match="could not be resolved") as error:
        await _validate_remote_image_url("https://missing.example.test/output.png")
    assert not isinstance(error.value, NexusOutcomeUnknown)


@pytest.mark.asyncio
@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"])
async def test_download_dns_with_any_nonpublic_address_stays_forbidden(monkeypatch, address):
    def resolve(*args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))
            for ip in ["93.184.216.34", address]
        ]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    with pytest.raises(RuntimeError, match="non-public") as error:
        await _validate_remote_image_url("https://unsafe.example.test/output.png")
    assert not isinstance(error.value, NexusOutcomeUnknown)


def test_questionnaire_aspect_ratio_inherits_source_shape() -> None:
    from types import SimpleNamespace

    from app.workers.generation_worker import _questionnaire_aspect_ratio

    assert _questionnaire_aspect_ratio(None) == "16:9"
    assert _questionnaire_aspect_ratio(SimpleNamespace(width=1920, height=1080)) == "16:9"
    assert _questionnaire_aspect_ratio(SimpleNamespace(width=2048, height=2048)) == "1:1"
    assert _questionnaire_aspect_ratio(SimpleNamespace(width=1200, height=1600)) == "3:4"
