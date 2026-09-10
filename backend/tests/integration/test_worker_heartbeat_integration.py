from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration

if os.getenv('RUN_INTEGRATION_TESTS') != '1':
    pytest.skip('set RUN_INTEGRATION_TESTS=1 with a migrated test database', allow_module_level=True)

from app.core.redis import redis_client  # noqa: E402
from app.workers.heartbeat import (  # noqa: E402
    heartbeat_key,
    touch_worker_heartbeat,
    worker_heartbeat_age,
)


@pytest.mark.asyncio
async def test_worker_heartbeat_roundtrip_in_redis() -> None:
    key = heartbeat_key('integration')
    await redis_client.delete(key)
    await touch_worker_heartbeat('integration')
    age = await worker_heartbeat_age('integration')
    assert age is not None
    assert 0 <= age < 5
    assert await redis_client.delete(key) == 1
