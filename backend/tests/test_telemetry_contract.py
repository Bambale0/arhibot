from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_metrics_are_blocked_by_public_nginx() -> None:
    inner = (REPO_ROOT / 'backend' / 'deploy' / 'nginx.conf').read_text()
    outer = (REPO_ROOT / 'backend' / 'deploy' / 'nginx-archibot.conf').read_text()
    assert 'location = /metrics' in inner and 'return 404;' in inner
    assert 'location = /metrics' in outer and 'return 404;' in outer


def test_release_sha_is_injected_into_python_services() -> None:
    compose = (REPO_ROOT / 'backend' / 'docker-compose.yml').read_text()
    assert compose.count('RELEASE_SHA: "${AUROOM_RELEASE_SHA:-unknown}"') == 5


def test_required_integration_gate_contains_real_redis_failure_probe() -> None:
    ci = (REPO_ROOT / '.github' / 'workflows' / 'ci.yml').read_text()
    assert 'Controlled Redis pause/recovery probe' in ci
    assert 'docker pause auroom-chaos-redis' in ci
    assert 'redis_failure_probe.py expect-down 3' in ci
