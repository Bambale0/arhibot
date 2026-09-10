from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_compose_has_resource_and_log_guardrails() -> None:
    compose = (REPO_ROOT / 'backend' / 'docker-compose.yml').read_text()
    assert 'x-default-logging: &default-logging' in compose
    assert 'AUROOM_API_MEMORY_LIMIT:-512m' in compose
    assert 'AUROOM_WORKER_MEMORY_LIMIT:-1536m' in compose
    assert 'AUROOM_POSTGRES_MEMORY_LIMIT:-1024m' in compose
    assert compose.count('logging: *default-logging') == 9


def test_deploy_installs_runtime_monitor_cron() -> None:
    deploy = (REPO_ROOT / 'ops' / 'deploy_docker.sh').read_text()
    assert 'AuRoom runtime monitor' in deploy
    assert 'runtime_monitor.sh' in deploy
    assert '*/15 * * * *' in deploy


def test_runtime_monitor_covers_preprod_failure_signals() -> None:
    monitor = (REPO_ROOT / 'ops' / 'runtime_monitor.sh').read_text()
    for token in (
        '/health/ready',
        'backups/runtime',
        'worker:generation',
        'broadcast-worker:broadcast',
        'maintenance:maintenance',
        'stale_generations',
        'RELEASE_SHA',
        'python -m app.ops_alert',
    ):
        assert token in monitor
