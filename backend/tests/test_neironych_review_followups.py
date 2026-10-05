import httpx
import pytest
from types import SimpleNamespace

from app.core.config import Settings
from app.ops.activate_dev_generation_routing import build_activation_payload
from app.providers import neironych
from app.providers.nexus import NexusOutcomeUnknown, NexusProviderError
from app.runtime_checks import _generation_provider_readiness
from app.schemas.admin import GenerationRuntimeUpdate
from app.services.generation_service import _public_quality_report
from app.workers.generation_worker import _reconciliation_report


def _provider() -> neironych.NeironychImageProvider:
    return neironych.NeironychImageProvider(Settings(neironych_api_key="test-only"))


def _request() -> dict:
    return {
        "model_name": "gpt-image-2.5-sunburst",
        "prompt": "Keep geometry",
        "image_url": None,
        "model_params": {},
        "idempotency_key": "auroom-review-followup",
    }


@pytest.mark.asyncio
async def test_definite_non_json_4xx_refunds_instead_of_reconciliation(monkeypatch) -> None:
    original = httpx.AsyncClient
    monkeypatch.setattr(
        neironych.httpx,
        "AsyncClient",
        lambda **kwargs: original(
            **kwargs,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(422, text="rejected by gateway")
            ),
        ),
    )
    with pytest.raises(NexusProviderError) as error:
        await _provider().generate(**_request())
    assert not isinstance(error.value, NexusOutcomeUnknown)
    assert "422" in str(error.value)


@pytest.mark.asyncio
async def test_ambiguous_response_preserves_safe_provider_request_id(monkeypatch) -> None:
    original = httpx.AsyncClient
    monkeypatch.setattr(
        neironych.httpx,
        "AsyncClient",
        lambda **kwargs: original(
            **kwargs,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    503,
                    text="temporarily unavailable",
                    headers={"X-Request-Id": "req-safe-503"},
                )
            ),
        ),
    )
    with pytest.raises(NexusOutcomeUnknown) as error:
        await _provider().generate(**_request())
    assert error.value.request_id == "req-safe-503"



@pytest.mark.asyncio
async def test_connect_timeout_before_submission_is_not_ambiguous(monkeypatch) -> None:
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            request = httpx.Request("POST", "https://api.example.test/v1/images/generations")
            raise httpx.ConnectTimeout("connect timed out", request=request)

    monkeypatch.setattr(neironych.httpx, "AsyncClient", lambda **kwargs: Client())
    with pytest.raises(NexusProviderError) as error:
        await _provider().generate(**_request())
    assert not isinstance(error.value, NexusOutcomeUnknown)
    assert error.value.retryable is True
    assert "connect" in str(error.value).lower()

def test_reconciliation_persists_request_id_in_private_checkpoint() -> None:
    original = {"provider_request": {"provider": "neironych", "state": "submitting"}}
    report = _reconciliation_report(original, "req-safe-503")
    assert report["requires_reconciliation"] is True
    assert report["provider_request"]["request_id"] == "req-safe-503"
    assert "request_id" not in original["provider_request"]


def test_public_report_redacts_provider_payload_urls_prompts_and_identifiers() -> None:
    private = {
        "provider_request": {
            "provider": "neironych",
            "state": "submitting",
            "key": "private-idempotency-key",
            "request_id": "provider-correlation-id",
            "request_body": {
                "prompt": "private prompt",
                "images": [{"image_url": "https://signed.example/input.png?token=secret"}],
            },
        }
    }
    public = _public_quality_report(private)
    assert public["provider_request"] == {"provider": "neironych", "state": "submitting"}
    assert private["provider_request"]["request_body"]["prompt"] == "private prompt"


def test_dev_activation_payload_preserves_quality_controls_and_replaces_routing() -> None:
    payload = build_activation_payload(
        {
            "primary_provider": "nexus",
            "fallback_provider": "nexus",
            "primary_model": "old",
            "fallback_model": "old-fallback",
            "primary_timeout_seconds": 90,
            "primary_params": {"steps": 20},
            "fallback_params": {"steps": 10},
            "mode_params": {"facade": {"guidance": 7}},
            "generation_quality_max_retries": 2,
            "updated_at": "not-editable",
        }
    )
    assert payload["primary_provider"] == payload["fallback_provider"] == "nexus"
    assert payload["primary_model"] == "gpt-image-2"
    assert payload["fallback_model"] == "nano-banana-pro"
    assert payload["primary_params"] == {}
    assert payload["fallback_params"] == {"image_size": "2K"}
    assert payload["mode_params"] == {}
    assert payload["generation_quality_max_retries"] == 2
    assert "updated_at" not in payload
    GenerationRuntimeUpdate.model_validate(payload)


def test_readiness_requires_credentials_for_configured_fallback() -> None:
    runtime = SimpleNamespace(
        primary_provider="neironych",
        primary_model="image-model",
        fallback_provider="nexus",
        fallback_model="fallback-model",
    )
    settings = Settings(neironych_api_key="configured", nexus_api_key=None)
    name, configured, secure = _generation_provider_readiness(runtime, settings)
    assert name == "neironych,nexus"
    assert configured is False
    assert secure is True
