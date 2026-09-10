from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from threading import Lock
from time import monotonic

import httpx

logger = logging.getLogger(__name__)


class CircuitOpenError(RuntimeError):
    def __init__(self, dependency: str, retry_after_seconds: float) -> None:
        super().__init__(f'{dependency} circuit is open')
        self.dependency = dependency
        self.retry_after_seconds = max(0.0, retry_after_seconds)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 2.0


class CircuitBreaker:
    def __init__(
        self,
        dependency: str,
        *,
        failure_threshold: int = 5,
        recovery_seconds: float = 30.0,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError('failure_threshold must be positive')
        if recovery_seconds <= 0:
            raise ValueError('recovery_seconds must be positive')
        self.dependency = dependency
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self._clock = clock
        self._lock = Lock()
        self._state = 'closed'
        self._failures = 0
        self._opened_at: float | None = None
        self._half_open_in_flight = False

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def before_call(self) -> None:
        with self._lock:
            if self._state == 'closed':
                return
            now = self._clock()
            opened_at = self._opened_at if self._opened_at is not None else now
            remaining = self.recovery_seconds - (now - opened_at)
            if self._state == 'open' and remaining <= 0 and not self._half_open_in_flight:
                self._state = 'half_open'
                self._half_open_in_flight = True
                return
            raise CircuitOpenError(self.dependency, max(0.0, remaining))

    def record_success(self) -> None:
        with self._lock:
            self._state = 'closed'
            self._failures = 0
            self._opened_at = None
            self._half_open_in_flight = False

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._state == 'half_open' or self._failures >= self.failure_threshold:
                self._state = 'open'
                self._opened_at = self._clock()
            self._half_open_in_flight = False

    def abort_call(self) -> None:
        with self._lock:
            if self._state == 'half_open':
                self._state = 'open'
                self._opened_at = self._clock()
                self._half_open_in_flight = False


_breakers: dict[tuple[str, int, float], CircuitBreaker] = {}
_breakers_lock = Lock()


def get_circuit_breaker(
    dependency: str, *, failure_threshold: int, recovery_seconds: float
) -> CircuitBreaker:
    key = (dependency, failure_threshold, recovery_seconds)
    with _breakers_lock:
        breaker = _breakers.get(key)
        if breaker is None:
            breaker = CircuitBreaker(
                dependency,
                failure_threshold=failure_threshold,
                recovery_seconds=recovery_seconds,
            )
            _breakers[key] = breaker
        return breaker


def reset_circuit_breakers() -> None:
    with _breakers_lock:
        _breakers.clear()


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get('retry-after')
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value >= 0 else None


def _retry_delay(policy: RetryPolicy, attempt: int, retry_after: float | None) -> float:
    delay = min(policy.max_delay_seconds, policy.base_delay_seconds * (2 ** max(attempt - 1, 0)))
    if retry_after is not None:
        delay = min(policy.max_delay_seconds, max(delay, retry_after))
    return delay * random.uniform(0.8, 1.2)


async def request_with_resilience(
    request: Callable[[], Awaitable[httpx.Response]],
    *,
    dependency: str,
    operation: str,
    breaker: CircuitBreaker,
    policy: RetryPolicy,
    retry_statuses: set[int] | None = None,
    deadline_monotonic: float | None = None,
) -> httpx.Response:
    retry_statuses = retry_statuses or {408, 429, 500, 502, 503, 504}
    last_error: Exception | None = None

    for attempt in range(1, policy.max_attempts + 1):
        remaining = None if deadline_monotonic is None else deadline_monotonic - monotonic()
        if remaining is not None and remaining <= 0:
            raise TimeoutError(f'{dependency} {operation} deadline exceeded')
        try:
            breaker.before_call()
        except CircuitOpenError:
            logger.warning(
                'Dependency circuit open',
                extra={
                    'dependency': dependency,
                    'operation': operation,
                    'attempt': attempt,
                    'circuit_state': breaker.state,
                },
            )
            raise

        try:
            response = (
                await request()
                if remaining is None
                else await asyncio.wait_for(request(), timeout=remaining)
            )
        except asyncio.CancelledError:
            breaker.abort_call()
            raise
        except (httpx.TransportError, TimeoutError) as exc:
            last_error = exc
            breaker.record_failure()
            if attempt >= policy.max_attempts or breaker.state == 'open':
                raise
            delay = _retry_delay(policy, attempt, None)
            logger.warning(
                'Retrying dependency transport failure',
                extra={
                    'dependency': dependency,
                    'operation': operation,
                    'attempt': attempt,
                    'circuit_state': breaker.state,
                    'retry_delay_ms': round(delay * 1000),
                },
            )
            if deadline_monotonic is not None:
                remaining_after = deadline_monotonic - monotonic()
                if remaining_after <= 0:
                    raise TimeoutError(f'{dependency} {operation} deadline exceeded') from exc
                delay = min(delay, remaining_after)
            await asyncio.sleep(delay)
            continue

        if response.status_code in retry_statuses:
            breaker.record_failure()
            retry_after = _retry_after_seconds(response)
            if retry_after is not None and retry_after > policy.max_delay_seconds:
                logger.warning(
                    'Dependency retry-after exceeds synchronous retry budget',
                    extra={
                        'dependency': dependency,
                        'operation': operation,
                        'attempt': attempt,
                        'status_code': response.status_code,
                        'circuit_state': breaker.state,
                        'retry_delay_ms': round(retry_after * 1000),
                    },
                )
                return response
            if attempt < policy.max_attempts and breaker.state != 'open':
                delay = _retry_delay(policy, attempt, retry_after)
                logger.warning(
                    'Retrying dependency response',
                    extra={
                        'dependency': dependency,
                        'operation': operation,
                        'attempt': attempt,
                        'status_code': response.status_code,
                        'circuit_state': breaker.state,
                        'retry_delay_ms': round(delay * 1000),
                    },
                )
                if deadline_monotonic is not None:
                    remaining_after = deadline_monotonic - monotonic()
                    if remaining_after <= 0:
                        raise TimeoutError(f'{dependency} {operation} deadline exceeded')
                    delay = min(delay, remaining_after)
                await asyncio.sleep(delay)
                continue
            return response

        breaker.record_success()
        return response

    if last_error is not None:
        raise last_error
    raise RuntimeError(f'{dependency} request attempts exhausted')
