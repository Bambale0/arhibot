from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from time import time

from app.core.redis import redis_client

logger = logging.getLogger(__name__)
HEARTBEAT_PREFIX = 'auroom:worker_heartbeat:'
HEARTBEAT_INTERVAL_SECONDS = 10
HEARTBEAT_TTL_SECONDS = 60


def heartbeat_key(worker_name: str) -> str:
    normalized = worker_name.strip().lower().replace('_', '-')
    if not normalized or any(char not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for char in normalized):
        raise ValueError('Invalid worker heartbeat name')
    return f'{HEARTBEAT_PREFIX}{normalized}'


async def touch_worker_heartbeat(worker_name: str) -> None:
    await redis_client.set(
        heartbeat_key(worker_name),
        f'{time():.6f}',
        ex=HEARTBEAT_TTL_SECONDS,
    )


async def worker_heartbeat_age(worker_name: str, *, now_epoch: float | None = None) -> float | None:
    raw = await redis_client.get(heartbeat_key(worker_name))
    if raw is None:
        return None
    try:
        recorded_at = float(raw)
    except (TypeError, ValueError):
        return None
    now = time() if now_epoch is None else now_epoch
    age = now - recorded_at
    if age < -5:
        return None
    return max(0.0, age)


async def worker_is_healthy(worker_name: str, *, max_age_seconds: float) -> bool:
    if max_age_seconds <= 0:
        raise ValueError('max_age_seconds must be positive')
    age = await worker_heartbeat_age(worker_name)
    return age is not None and age <= max_age_seconds


async def _heartbeat_loop(worker_name: str) -> None:
    while True:
        try:
            await touch_worker_heartbeat(worker_name)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('Worker heartbeat update failed for %s', worker_name)
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)


@asynccontextmanager
async def worker_heartbeat(worker_name: str) -> AsyncIterator[None]:
    try:
        await touch_worker_heartbeat(worker_name)
    except Exception:
        logger.exception('Initial worker heartbeat failed for %s', worker_name)
    task = asyncio.create_task(_heartbeat_loop(worker_name), name=f'heartbeat:{worker_name}')
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        try:
            await redis_client.delete(heartbeat_key(worker_name))
        except Exception:
            logger.warning('Could not remove worker heartbeat for %s', worker_name, exc_info=True)


async def _check_cli(worker_name: str, max_age_seconds: float) -> int:
    try:
        age = await worker_heartbeat_age(worker_name)
        if age is None or age > max_age_seconds:
            print(f'worker={worker_name} healthy=false age={age}', file=sys.stderr)
            return 1
        print(f'worker={worker_name} healthy=true age_seconds={age:.1f}')
        return 0
    finally:
        await redis_client.aclose()


def main() -> None:
    if len(sys.argv) != 4 or sys.argv[1] != 'check':
        raise SystemExit('usage: python -m app.workers.heartbeat check <worker> <max-age-seconds>')
    try:
        max_age = float(sys.argv[3])
    except ValueError as exc:
        raise SystemExit('max-age-seconds must be numeric') from exc
    raise SystemExit(asyncio.run(_check_cli(sys.argv[2], max_age)))


if __name__ == '__main__':
    main()
