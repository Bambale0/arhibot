import base64
from io import BytesIO
import httpx
import pytest
from PIL import Image
from app.core.config import Settings
from app.providers import neironych
from app.providers.nexus import NexusOutcomeUnknown, NexusProviderError


def image():
    f = BytesIO()
    Image.new('RGB', (16, 9), 'white').save(f, format='PNG')
    return f.getvalue()


def provider():
    return neironych.NeironychImageProvider(Settings(neironych_api_key='test-only'))


def request(**values):
    return dict(model_name='gpt-image-2.5-sunburst', prompt='Keep geometry', image_url=None,
                model_params={}, idempotency_key='auroom-test-generation', **values)


def mock_client(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(neironych.httpx, 'AsyncClient', lambda **kw: original(**kw, transport=httpx.MockTransport(handler)))


@pytest.mark.asyncio
async def test_generation_decodes_image_without_polling(monkeypatch):
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(image()).decode()}]}, headers={'X-Request-Id': 'req-test'})
    mock_client(monkeypatch, handler)
    result = await provider().generate(**request())
    assert result.image_data == image()
    assert result.task_id == 'sync'
    assert result.request_id == 'req-test'
    assert len(calls) == 1
    assert calls[0].url.path == '/v1/images/generations'
    assert calls[0].headers['Idempotency-Key'] == 'auroom-test-generation'
    assert calls[0].headers['Authorization'] == 'Bearer test-only'
    assert 'x-api-key' not in calls[0].headers


def test_edit_payload_protects_inputs_and_paid_count():
    endpoint, body = provider().build_request(model_name='gpt-image-2.5-sunburst', prompt='real',
        image_url='https://media.example/base.png', reference_image_urls=['https://media.example/guide.png'],
        model_params={'model':'forged', 'prompt':'forged', 'images':[], 'mask':{}, 'n':5, 'response_format':'url', 'aspect_ratio':'16:9', 'quality':'high', 'size':'3840x2160'})
    assert endpoint == '/v1/images/edits'
    assert body['model'] == 'gpt-image-2.5-sunburst'
    assert body['prompt'].startswith('real\n')
    assert body['images'] == [{'image_url':'https://media.example/base.png'}, {'image_url':'https://media.example/guide.png'}]
    assert body['n'] == 1 and body['response_format'] == 'b64_json'
    assert 'mask' not in body and 'aspect_ratio' not in body


@pytest.mark.asyncio
@pytest.mark.parametrize('status,body', [(409, {'detail':'request_already_submitted'}), (503, {'detail':'submission_outcome_unknown'}), (200, {'data': []}), (200, {'data':[{'url':'https://[broken/image.png'}]}), (200, {'data':[{'b64_json':'bm90IGFuIGltYWdl'}]})])
async def test_ambiguous_result_never_retries_or_allows_fallback(monkeypatch, status, body):
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(status, json=body)
    mock_client(monkeypatch, handler)
    with pytest.raises(NexusOutcomeUnknown) as error:
        await provider().generate(**request())
    assert error.value.retryable is False and len(calls) == 1


@pytest.mark.asyncio
async def test_timeout_never_retries(monkeypatch):
    calls = []
    def handler(req):
        calls.append(req)
        raise httpx.ReadTimeout('lost', request=req)
    mock_client(monkeypatch, handler)
    with pytest.raises(NexusOutcomeUnknown):
        await provider().generate(**request())
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_sync_resume_never_resubmits(monkeypatch):
    def handler(req):
        pytest.fail('Sync request cannot be polled or replayed')
    mock_client(monkeypatch, handler)
    with pytest.raises(NexusOutcomeUnknown):
        await provider().generate(**request(task_id='sync'))


@pytest.mark.asyncio
async def test_rejection_has_safe_diagnostics(monkeypatch):
    mock_client(monkeypatch, lambda req: httpx.Response(402, json={'error':{'type':'insufficient_balance','message':'secret text'}}, headers={'X-Request-Id':'req-safe'}))
    with pytest.raises(NexusProviderError) as error:
        await provider().generate(**request())
    assert not isinstance(error.value, NexusOutcomeUnknown)
    assert error.value.retryable is False
    assert 'insufficient_balance' in str(error.value) and 'secret text' not in str(error.value)

@pytest.mark.asyncio
async def test_worker_uses_inline_bytes_without_network(monkeypatch):
    from app.workers import generation_worker as worker
    async def forbidden(*args):
        pytest.fail('inline image must not be downloaded')
    monkeypatch.setattr(worker, '_download_image', forbidden)
    result = neironych.NeironychImageResult('sync', '', image(), 'req-id')
    assert await worker._provider_image_data(result, Settings()) == image()


def test_worker_factory_routes_explicit_provider():
    from app.workers import generation_worker as worker
    assert isinstance(worker._image_provider('neironych', Settings(neironych_api_key='test-only')), neironych.NeironychImageProvider)
    with pytest.raises(NexusProviderError):
        worker._image_provider('unknown', Settings())

@pytest.mark.parametrize('params', [{'output_format':'png'}, {'resolution':'2K'}, {'quality':'invalid'}, {'aspect_ratio':'16:9'}])
def test_unsupported_configuration_fails_before_purchase(params):
    with pytest.raises(NexusProviderError) as error:
        provider().build_request(model_name='gpt-image-2.5-sunburst', prompt='test', image_url=None, model_params=params)
    assert not error.value.retryable


def test_geometry_uses_configured_resolution_without_nexus_parameter():
    _, body = provider().build_request(model_name='gpt-image-2.5-sunburst', prompt='test', image_url=None,
                                      model_params={'size':'2048x2048', 'aspect_ratio':'16:9'})
    assert body['size'] == '2048x1152'
    assert 'aspect_ratio' not in body


@pytest.mark.asyncio
async def test_url_image_invalid_bytes_keep_reconciliation(monkeypatch):
    from app.workers import generation_worker as worker
    async def invalid(*args):
        return b"not an image"
    monkeypatch.setattr(worker, "_download_image", invalid)
    result = neironych.NeironychImageResult("sync", "https://cdn.example/image.png")
    with pytest.raises(NexusOutcomeUnknown):
        await worker._provider_image_data(result, Settings())
