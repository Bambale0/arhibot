from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from app.core.config import Settings
from app.core.resilience import reset_circuit_breakers
from app.providers.nexus import NexusImageProvider, NexusProviderError, NexusOutcomeUnknown
from app.providers.yookassa import YooKassaError, YooKassaProvider


@pytest.fixture(autouse=True)
def _reset_breakers() -> None:
    reset_circuit_breakers()


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        'app_env': 'test',
        'nexus_api_key': 'test-key',
        'nexus_retry_attempts': 3,
        'yookassa_shop_id': 'shop',
        'yookassa_secret_key': 'secret',
        'yookassa_retry_attempts': 3,
    }
    values.update(overrides)
    return Settings(**values)


class _FakeAsyncClient:
    responses: list[object] = []
    calls = 0

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, *args: object, **kwargs: object) -> httpx.Response:
        type(self).calls += 1
        item = type(self).responses.pop(0)
        if isinstance(item, Exception):
            raise item
        assert isinstance(item, httpx.Response)
        return item

    async def get(self, *args: object, **kwargs: object) -> httpx.Response:
        return await self.post(*args, **kwargs)


@pytest.mark.asyncio
async def test_nexus_does_not_repeat_ambiguous_paid_create(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeAsyncClient.calls = 0
    _FakeAsyncClient.responses = [
        httpx.Response(503, json={'error': 'busy'}),
        httpx.Response(200, json={'image_url': 'https://cdn.example.test/result.png'}),
    ]

    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr('app.providers.nexus.httpx.AsyncClient', _FakeAsyncClient)
    monkeypatch.setattr('app.core.resilience.asyncio.sleep', no_sleep)
    with pytest.raises(NexusProviderError) as error:
        await NexusImageProvider(_settings()).generate(
            model_name='model', prompt='prompt', image_url=None,
            model_params={}, idempotency_key='stable-key',
        )
    assert error.value.retryable is False
    assert _FakeAsyncClient.calls == 1



@pytest.mark.asyncio
async def test_yookassa_retries_transport_failure_and_keeps_idempotent_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = httpx.Request('POST', 'https://api.yookassa.ru/v3/payments')
    _FakeAsyncClient.calls = 0
    _FakeAsyncClient.responses = [
        httpx.ConnectError('temporary', request=request),
        httpx.Response(
            200,
            json={
                'id': 'pay-1',
                'status': 'pending',
                'amount': {'value': '10.00', 'currency': 'RUB'},
                'metadata': {'billing_payment_id': 'local-1'},
                'confirmation': {'confirmation_url': 'https://pay.example.test'},
            },
        ),
    ]

    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr('app.providers.yookassa.httpx.AsyncClient', _FakeAsyncClient)
    monkeypatch.setattr('app.core.resilience.asyncio.sleep', no_sleep)
    result = await YooKassaProvider(_settings()).create_payment(
        amount=Decimal('10.00'),
        currency='RUB',
        description='test',
        return_url='https://example.test/return',
        metadata={'billing_payment_id': 'local-1'},
        idempotence_key='stable-key',
    )
    assert result.id == 'pay-1'
    assert _FakeAsyncClient.calls == 2


def test_yookassa_invalid_success_json_is_normalized() -> None:
    response = httpx.Response(200, text='not-json')
    with pytest.raises(YooKassaError, match='invalid JSON'):
        YooKassaProvider._parse_payment(response, operation='get payment')


@pytest.mark.asyncio
async def test_yookassa_mutating_5xx_is_marked_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeAsyncClient.calls = 0
    _FakeAsyncClient.responses = [httpx.Response(503, json={"description": "busy"})] * 3

    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("app.providers.yookassa.httpx.AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr("app.core.resilience.asyncio.sleep", no_sleep)
    with pytest.raises(YooKassaError) as exc_info:
        await YooKassaProvider(_settings()).create_refund(
            payment_id="pay-1",
            amount=Decimal("10.00"),
            currency="RUB",
            description="refund",
            idempotence_key="stable-refund-key",
        )
    assert exc_info.value.ambiguous is True
    assert _FakeAsyncClient.calls == 3


@pytest.mark.asyncio
async def test_nexus_accepted_task_survives_primary_soft_timeout(monkeypatch):
    clock = [0.0]
    async def sleep(delay):
        clock[0] += delay
    monkeypatch.setattr('app.providers.nexus.monotonic', lambda: clock[0])
    monkeypatch.setattr('app.core.resilience.monotonic', lambda: clock[0])
    monkeypatch.setattr('app.providers.nexus.asyncio.sleep', sleep)
    monkeypatch.setattr('app.providers.nexus.httpx.AsyncClient', _FakeAsyncClient)
    _FakeAsyncClient.calls = 0
    _FakeAsyncClient.responses = [httpx.Response(202,json={'task_id':'accepted-1'})]
    _FakeAsyncClient.responses += [httpx.Response(200,json={'status':'processing'})] * 4
    _FakeAsyncClient.responses += [httpx.Response(200,json={'status':'completed','result':{'image_url':'https://cdn.example.test/result.png'}})]
    result = await NexusImageProvider(_settings(nexus_poll_interval_seconds=30,nexus_task_timeout_seconds=180)).generate(
        model_name='model', prompt='prompt', image_url=None, model_params={}, idempotency_key='stable-key', timeout_seconds=90,
    )
    assert result.task_id == 'accepted-1'
    assert clock[0] == 120
    assert _FakeAsyncClient.calls == 6


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', [
    httpx.ReadTimeout('lost create response'),
    httpx.Response(408, json={'detail':'timeout'}),
    httpx.Response(503, json={'detail':'busy'}),
    httpx.Response(200, text='broken-json'),
    httpx.Response(200, json=[]),
])
async def test_nexus_unknown_create_outcome_is_not_safe_to_fallback(monkeypatch, outcome):
    monkeypatch.setattr('app.providers.nexus.httpx.AsyncClient', _FakeAsyncClient)
    _FakeAsyncClient.calls = 0
    _FakeAsyncClient.responses = [outcome]
    with pytest.raises(NexusOutcomeUnknown) as error:
        await NexusImageProvider(_settings()).generate(model_name='model',prompt='prompt',image_url=None,model_params={},idempotency_key='key')
    assert not error.value.retryable
    assert _FakeAsyncClient.calls == 1


@pytest.mark.asyncio
async def test_nexus_resume_only_polls_existing_task(monkeypatch):
    class PollOnly(_FakeAsyncClient):
        async def post(self, *args, **kwargs):
            pytest.fail('A recovered accepted task must never be recreated')
        async def get(self, *args, **kwargs):
            assert args[0].endswith('/tasks/existing-task')
            return httpx.Response(200,json={'status':'completed','image_url':'https://cdn.example.test/recovered.png'})
    monkeypatch.setattr('app.providers.nexus.httpx.AsyncClient', PollOnly)
    result=await NexusImageProvider(_settings()).generate(model_name='model',prompt='prompt',image_url=None,model_params={},idempotency_key='key',task_id='existing-task')
    assert result.task_id == 'existing-task'


@pytest.mark.asyncio
@pytest.mark.parametrize(('task_response','retryable'), [
    (httpx.Response(200,json={'status':'failed'}), True),
    (httpx.Response(200,text='broken-json'), False),
    (httpx.Response(404,json={'detail':'unknown task'}), False),
])
async def test_nexus_only_terminal_task_failure_allows_fallback(monkeypatch, task_response, retryable):
    monkeypatch.setattr('app.providers.nexus.httpx.AsyncClient', _FakeAsyncClient)
    _FakeAsyncClient.responses=[task_response]
    with pytest.raises(NexusProviderError) as error:
        await NexusImageProvider(_settings()).generate(model_name='model',prompt='prompt',image_url=None,model_params={},idempotency_key='key',task_id='existing')
    assert error.value.retryable is retryable
