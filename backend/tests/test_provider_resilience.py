from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from app.core.config import Settings
from app.core.resilience import reset_circuit_breakers
from app.providers.nexus import NexusImageProvider
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
async def test_nexus_retries_transient_create_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeAsyncClient.calls = 0
    _FakeAsyncClient.responses = [
        httpx.Response(503, json={'error': 'busy'}),
        httpx.Response(200, json={'image_url': 'https://cdn.example.test/result.png'}),
    ]

    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr('app.providers.nexus.httpx.AsyncClient', _FakeAsyncClient)
    monkeypatch.setattr('app.core.resilience.asyncio.sleep', no_sleep)
    result = await NexusImageProvider(_settings()).generate(
        model_name='model',
        prompt='prompt',
        image_url=None,
        model_params={},
        idempotency_key='stable-key',
    )
    assert result.image_url == 'https://cdn.example.test/result.png'
    assert _FakeAsyncClient.calls == 2


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
