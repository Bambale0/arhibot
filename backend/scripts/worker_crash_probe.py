from __future__ import annotations

import asyncio
import sys

from app.core.redis import redis_client
from app.workers.heartbeat import worker_heartbeat, worker_singleton


async def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: worker_crash_probe.py <worker-name>")
    worker_name = sys.argv[1]

    try:
        async with worker_singleton(worker_name), worker_heartbeat(worker_name):
            print(f"worker_crash_probe worker={worker_name} state=ready", flush=True)
            while True:
                await asyncio.sleep(60)
    finally:
        await redis_client.aclose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
