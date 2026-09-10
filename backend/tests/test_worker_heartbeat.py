from __future__ import annotations

from pathlib import Path

import pytest

from app.workers import heartbeat

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_heartbeat_key_rejects_unsafe_names() -> None:
    assert heartbeat.heartbeat_key('generation') == 'auroom:worker_heartbeat:generation'
    with pytest.raises(ValueError):
        heartbeat.heartbeat_key('../worker')


@pytest.mark.asyncio
async def test_heartbeat_age(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get(key: str) -> str | None:
        assert key == 'auroom:worker_heartbeat:generation'
        return '100.0'

    monkeypatch.setattr(heartbeat.redis_client, 'get', fake_get)
    assert await heartbeat.worker_heartbeat_age('generation', now_epoch=112.5) == 12.5


@pytest.mark.asyncio
async def test_heartbeat_rejects_missing_or_future_value(monkeypatch: pytest.MonkeyPatch) -> None:
    values = iter([None, '200.0'])

    async def fake_get(_key: str) -> str | None:
        return next(values)

    monkeypatch.setattr(heartbeat.redis_client, 'get', fake_get)
    assert await heartbeat.worker_heartbeat_age('generation', now_epoch=100.0) is None
    assert await heartbeat.worker_heartbeat_age('generation', now_epoch=100.0) is None


def test_compose_and_deploy_require_worker_health() -> None:
    compose = (REPO_ROOT / 'backend' / 'docker-compose.yml').read_text()
    deploy = (REPO_ROOT / 'ops' / 'deploy_docker.sh').read_text()
    smoke = (REPO_ROOT / '.github' / 'workflows' / 'server-smoke.yml').read_text()

    for worker_name in ('generation', 'broadcast', 'maintenance'):
        assert f'app.workers.heartbeat\", \"check\", \"{worker_name}\", \"45\"' in compose
    assert 'for service in worker broadcast-worker maintenance frontend; do' in deploy
    assert 'for service in maintenance worker broadcast-worker frontend postgres redis; do' in smoke
