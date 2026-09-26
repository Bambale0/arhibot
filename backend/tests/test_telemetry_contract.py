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

def test_required_integration_gate_contains_worker_sigkill_recovery_probe() -> None:
    ci = (REPO_ROOT / '.github' / 'workflows' / 'ci.yml').read_text()
    probe = (REPO_ROOT / 'backend' / 'scripts' / 'worker_crash_probe.py').read_text()

    assert 'Controlled worker SIGKILL recovery probe' in ci
    assert 'kill -9 "${first_pid}"' in ci
    assert 'Replacement worker exited instead of waiting for the stale singleton lease' in ci
    assert 'Replacement worker acquired the singleton lease before stale-owner expiry' in ci
    assert 'Replacement worker did not acquire the lease after stale-owner expiry' in ci
    assert 'Worker SIGKILL recovery probe passed without restart loop' in ci

    assert 'worker_singleton' in probe
    assert 'worker_heartbeat' in probe
    assert 'state=ready' in probe

