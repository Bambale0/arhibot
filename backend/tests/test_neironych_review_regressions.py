import base64
import struct
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import pytest
from PIL import Image

from app.core.config import Settings
from app.domain.generations.enums import GenerationStatus
from app.providers import neironych
from app.providers.nexus import NexusOutcomeUnknown
from app.services.asset_service import LocalMediaStorage
from app.workers import generation_worker as worker


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 9), "white").save(output, format="PNG")
    return output.getvalue()


def _bad_crc_png() -> bytes:
    data = bytearray(_png())
    offset = 8
    while offset < len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        if data[offset + 4:offset + 8] == b"IDAT":
            data[offset + 8 + length] ^= 1
            return bytes(data)
        offset += length + 12
    raise AssertionError("PNG fixture must contain an IDAT chunk")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "item",
    [
        {"url": "https://[broken/image.png"},
        {"b64_json": base64.b64encode(_bad_crc_png()).decode()},
    ],
)
async def test_malformed_success_always_preserves_reconciliation(monkeypatch, item):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={"data": [item]})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        neironych.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(**kwargs, transport=httpx.MockTransport(handle)),
    )
    provider = neironych.NeironychImageProvider(Settings(neironych_api_key="test-only"))
    with pytest.raises(NexusOutcomeUnknown) as error:
        await provider.generate(
            model_name="image-model",
            prompt="Preserve this scene",
            image_url=None,
            model_params={},
            idempotency_key="review-malformed-success",
        )
    assert error.value.retryable is False
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("image_data", [b"not an image", _bad_crc_png()])
async def test_invalid_url_image_bytes_preserve_reconciliation(monkeypatch, image_data):
    download = AsyncMock(return_value=image_data)
    monkeypatch.setattr(worker, "_download_image", download)
    result = neironych.NeironychImageResult("sync", "https://cdn.example.test/image.png")
    with pytest.raises(NexusOutcomeUnknown) as error:
        await worker._provider_image_data(result, Settings())
    assert error.value.retryable is False
    download.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("task_id", [None, "sync"])
async def test_saved_unknown_purchase_is_checked_before_changed_runtime_params(
    monkeypatch, task_id
):
    generation_id = uuid4()
    checkpoint = {
        "key": f"auroom-{generation_id}-primary",
        "provider": "neironych",
        "task_id": task_id,
        "state": "submitting" if task_id is None else "accepted",
        "model": "original-image-model",
    }
    row = SimpleNamespace(
        status=GenerationStatus.PROCESSING,
        quality_report={"provider_request": checkpoint},
    )
    session = AsyncMock()
    session.__aenter__.return_value = session
    repository = SimpleNamespace(get_for_update=AsyncMock(return_value=row))
    monkeypatch.setattr(worker, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(worker, "GenerationRepository", lambda db: repository)
    provider = neironych.NeironychImageProvider(Settings(neironych_api_key="test-only"))
    submit = AsyncMock(side_effect=AssertionError("Saved purchase must never be resubmitted"))
    monkeypatch.setattr(provider, "generate", submit)

    with pytest.raises(NexusOutcomeUnknown):
        await worker._generate_checkpointed(
            provider,
            generation_id,
            attempt=0,
            phase="primary",
            model_name="new-model",
            prompt="Current runtime differs from the original submission",
            source_url=None,
            params={"unsupported_changed_by_admin": True},
            reference_image_urls=None,
            timeout_seconds=None,
        )
    submit.assert_not_awaited()
    session.commit.assert_not_awaited()
    assert row.quality_report["provider_request"] == checkpoint


@pytest.mark.asyncio
async def test_inline_flyover_frames_chain_signed_persisted_images(monkeypatch, tmp_path):
    settings = Settings(
        media_root=str(tmp_path),
        media_public_base_url="https://media.example.test",
        neironych_api_key="test-only",
    )
    generation_id = uuid4()
    row = SimpleNamespace(status=GenerationStatus.PROCESSING, quality_report={})
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.get.return_value = row
    repository = SimpleNamespace(get_for_update=AsyncMock(return_value=row))
    monkeypatch.setattr(worker, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(worker, "GenerationRepository", lambda db: repository)
    requests = []

    async def generate(provider, unused_generation_id, **kwargs):
        endpoint, body = provider.build_request(
            model_name=kwargs["model_name"],
            prompt=kwargs["prompt"],
            image_url=kwargs["source_url"],
            model_params=kwargs["params"],
        )
        requests.append((kwargs["source_url"], endpoint, body))
        return neironych.NeironychImageResult("sync", "", _png())

    monkeypatch.setattr(worker, "_generate_checkpointed", generate)
    frames, task_id = await worker._generate_flyover_frames(
        provider=neironych.NeironychImageProvider(settings),
        generation_id=generation_id,
        model_name="image-model",
        prompt="Move the camera",
        params={},
        source_url="https://media.example.test/original.png",
        keyframe_count=4,
        settings=settings,
    )

    assert frames == [_png()] * 3
    assert task_id == "sync"
    assert len(requests) == 3
    assert all(endpoint == "/v1/images/edits" for _, endpoint, _ in requests)
    assert all(body["images"] == [{"image_url": source}] for source, _, body in requests)
    storage = LocalMediaStorage(settings)
    for index, (source, _, _) in enumerate(requests[1:], start=1):
        path = f"internal/admin-frames/{generation_id}/flyover-{index}.png"
        parsed = urlsplit(source)
        query = parse_qs(parsed.query)
        assert parsed.path == f"/api/v1/media/{path}"
        assert storage.absolute_path(path).read_bytes() == _png()
        assert storage.verify_signature(
            path,
            expires=int(query["expires"][0]),
            signature=query["signature"][0],
        )
