from __future__ import annotations

import asyncio
import sys
from time import monotonic

from sqlalchemy import text

from app.db.session import dispose_engine, get_engine


async def _database_ok(max_seconds: float) -> tuple[bool, Exception | None]:
    async def probe() -> None:
        async with get_engine().connect() as connection:
            await connection.execute(text("SELECT 1"))

    error: Exception | None = None
    try:
        await asyncio.wait_for(probe(), timeout=max_seconds)
        return True, None
    except Exception as exc:
        error = exc
        return False, error
    finally:
        await dispose_engine()


async def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in {"expect-up", "expect-down"}:
        raise SystemExit("usage: postgres_failure_probe.py <expect-up|expect-down> <max-seconds>")
    expected_up = sys.argv[1] == "expect-up"
    max_seconds = float(sys.argv[2])
    if max_seconds <= 0:
        raise SystemExit("max-seconds must be positive")

    started = monotonic()
    ok, error = await _database_ok(max_seconds)
    elapsed = monotonic() - started

    print(
        f"postgres_probe expected_up={expected_up} ok={ok} elapsed_seconds={elapsed:.3f} "
        f"error={type(error).__name__ if error else 'none'}"
    )
    if elapsed > max_seconds + 0.5:
        print(f"PostgreSQL probe exceeded {max_seconds}s bound", file=sys.stderr)
        return 1
    return 0 if ok is expected_up else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
