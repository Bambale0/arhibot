from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration

if os.getenv('RUN_INTEGRATION_TESTS') != '1':
    pytest.skip('set RUN_INTEGRATION_TESTS=1 with a migrated test database', allow_module_level=True)

from app.main import app  # noqa: E402


@pytest.mark.asyncio
async def test_version_and_metrics_are_available_inside_api() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        version = await client.get('/health/version')
        assert version.status_code == 200, version.text
        payload = version.json()
        assert payload['environment'] == 'test'
        assert payload['release_sha']

        await client.get('/api/v1/questionnaires')
        raw_id = '11111111-1111-1111-1111-111111111111'
        await client.get(f'/api/v1/projects/{raw_id}')
        metrics = await client.get('/metrics')

    assert metrics.status_code == 200, metrics.text
    body = metrics.text
    assert 'auroom_http_requests_total' in body
    assert 'route="/api/v1/questionnaires"' in body
    assert 'route="/api/v1/projects/{project_id}"' in body
    assert raw_id not in body
    assert 'auroom_queue_depth' in body
    assert 'auroom_worker_heartbeat_age_seconds' in body
    assert 'auroom_generations_in_state' in body
    assert 'auroom_build_info' in body
