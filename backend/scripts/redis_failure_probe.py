from __future__ import annotations

import asyncio
import sys
from time import monotonic

from app.core.redis import redis_client


async def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in {'expect-up', 'expect-down'}:
        raise SystemExit('usage: redis_failure_probe.py <expect-up|expect-down> <max-seconds>')
    expected_up = sys.argv[1] == 'expect-up'
    max_seconds = float(sys.argv[2])
    if max_seconds <= 0:
        raise SystemExit('max-seconds must be positive')

    started = monotonic()
    error: Exception | None = None
    try:
        ok = await redis_client.ping()
    except Exception as exc:
        ok = False
        error = exc
    finally:
        await redis_client.aclose()
    elapsed = monotonic() - started

    print(
        f'redis_probe expected_up={expected_up} ok={ok} elapsed_seconds={elapsed:.3f} '
        f'error={type(error).__name__ if error else "none"}'
    )
    if elapsed > max_seconds:
        print(f'Redis probe exceeded {max_seconds}s bound', file=sys.stderr)
        return 1
    return 0 if ok is expected_up else 1


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
