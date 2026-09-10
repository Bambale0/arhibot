from __future__ import annotations

import httpx
import pytest

from app.core.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    RetryPolicy,
    request_with_resilience,
)


def test_circuit_breaker_opens_and_recovers_with_single_half_open_probe() -> None:
    now = [100.0]
    breaker = CircuitBreaker('test', failure_threshold=2, recovery_seconds=10, clock=lambda: now[0])
    breaker.record_failure()
    assert breaker.state == 'closed'
    breaker.record_failure()
    assert breaker.state == 'open'
    with pytest.raises(CircuitOpenError):
        breaker.before_call()
    now[0] += 11
    breaker.before_call()
    assert breaker.state == 'half_open'
    with pytest.raises(CircuitOpenError):
        breaker.before_call()
    breaker.record_success()
    assert breaker.state == 'closed'


@pytest.mark.asyncio
async def test_request_retries_retryable_status_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [httpx.Response(503), httpx.Response(200)]
    calls = 0
    sleeps: list[float] = []

    async def request() -> httpx.Response:
        nonlocal calls
        calls += 1
        return responses.pop(0)

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr('app.core.resilience.asyncio.sleep', fake_sleep)
    monkeypatch.setattr('app.core.resilience.random.uniform', lambda _a, _b: 1.0)
    breaker = CircuitBreaker('test', failure_threshold=5, recovery_seconds=30)
    response = await request_with_resilience(
        request,
        dependency='test',
        operation='probe',
        breaker=breaker,
        policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.1, max_delay_seconds=1),
    )
    assert response.status_code == 200
    assert calls == 2
    assert sleeps == [0.1]
    assert breaker.state == 'closed'


@pytest.mark.asyncio
async def test_request_fails_fast_when_circuit_is_open() -> None:
    calls = 0

    async def request() -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200)

    breaker = CircuitBreaker('test', failure_threshold=1, recovery_seconds=30)
    breaker.record_failure()
    with pytest.raises(CircuitOpenError):
        await request_with_resilience(
            request,
            dependency='test',
            operation='probe',
            breaker=breaker,
            policy=RetryPolicy(max_attempts=3),
        )
    assert calls == 0


@pytest.mark.asyncio
async def test_long_retry_after_is_not_retried_early(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    sleeps: list[float] = []

    async def request() -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={'Retry-After': '60'})

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr('app.core.resilience.asyncio.sleep', fake_sleep)
    breaker = CircuitBreaker('test', failure_threshold=5, recovery_seconds=30)
    response = await request_with_resilience(
        request,
        dependency='test',
        operation='rate_limited',
        breaker=breaker,
        policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.1, max_delay_seconds=2),
    )
    assert response.status_code == 429
    assert calls == 1
    assert sleeps == []
