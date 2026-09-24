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


@pytest.mark.asyncio
async def test_worker_singleton_uses_owner_checked_lease(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []

    async def fake_set(key: str, value: str, *, ex: int | None = None, nx: bool = False) -> bool:
        calls.append(("set", key, ex, nx, value))
        return True

    async def fake_eval(script: str, numkeys: int, *values):
        calls.append(("eval", numkeys, values, script))
        return 1

    monkeypatch.setattr(heartbeat.redis_client, "set", fake_set)
    monkeypatch.setattr(heartbeat.redis_client, "eval", fake_eval)

    async with heartbeat.worker_singleton("generation"):
        assert calls[0][0:4] == (
            "set",
            "auroom:worker_lease:generation",
            heartbeat.WORKER_LEASE_TTL_SECONDS,
            True,
        )

    release = next(item for item in calls if item[0] == "eval")
    assert release[1] == 1
    assert release[2][0] == "auroom:worker_lease:generation"


@pytest.mark.asyncio
async def test_worker_singleton_rejects_second_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_set(*args, **kwargs):  # noqa: ANN002, ANN003
        return False

    monkeypatch.setattr(heartbeat.redis_client, "set", fake_set)
    with pytest.raises(RuntimeError, match="already owns"):
        async with heartbeat.worker_singleton("generation"):
            pass


@pytest.mark.asyncio
async def test_worker_singleton_waits_for_stale_lease_before_starting(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = iter([False, False, True])
    sleeps: list[float] = []
    calls: list[tuple] = []

    async def fake_set(key: str, value: str, *, ex: int | None = None, nx: bool = False) -> bool:
        calls.append(("set", key, ex, nx, value))
        return next(attempts)

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    async def fake_eval(script: str, numkeys: int, *values):
        calls.append(("eval", numkeys, values, script))
        return 1

    monkeypatch.setattr(heartbeat.redis_client, "set", fake_set)
    monkeypatch.setattr(heartbeat.redis_client, "eval", fake_eval)
    monkeypatch.setattr(heartbeat.asyncio, "sleep", fake_sleep)

    async with heartbeat.worker_singleton("generation"):
        pass

    assert sleeps == [
        heartbeat.WORKER_LEASE_ACQUIRE_POLL_SECONDS,
        heartbeat.WORKER_LEASE_ACQUIRE_POLL_SECONDS,
    ]
    assert [item[0] for item in calls].count("set") == 3


def test_compose_orders_api_consumers_after_readiness() -> None:
    compose = (REPO_ROOT / 'backend' / 'docker-compose.yml').read_text()

    assert 'health/ready' in compose
    assert 'api:\n        condition: service_healthy' in compose
    assert 'frontend:\n        condition: service_healthy' in compose

def test_compose_and_deploy_require_worker_health() -> None:
    compose = (REPO_ROOT / 'backend' / 'docker-compose.yml').read_text()
    deploy = (REPO_ROOT / 'ops' / 'deploy_docker.sh').read_text()
    smoke = (REPO_ROOT / '.github' / 'workflows' / 'server-smoke.yml').read_text()

    for worker_name in ('generation', 'broadcast', 'maintenance'):
        assert f'app.workers.heartbeat\", \"check\", \"{worker_name}\", \"45\"' in compose
    assert 'for service in worker broadcast-worker maintenance frontend; do' in deploy
    assert 'for service in maintenance worker broadcast-worker frontend postgres redis; do' in smoke
