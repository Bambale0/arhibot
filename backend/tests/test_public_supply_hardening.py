from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from app.main import app, documentation_enabled

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_documentation_is_available_outside_production() -> None:
    assert documentation_enabled is True
    assert app.openapi_url == '/openapi.json'
    assert app.docs_url == '/docs'
    assert app.redoc_url == '/redoc'


def test_public_nginx_denies_internal_docs_and_has_security_headers() -> None:
    nginx = (REPO_ROOT / 'backend' / 'deploy' / 'nginx-archibot.conf').read_text()
    assert nginx.count('server_tokens off;') == 2
    for path in ('/openapi.json', '/docs', '/redoc', '/metrics'):
        assert f'location = {path}' in nginx
    for header in (
        'Strict-Transport-Security',
        'X-Content-Type-Options',
        'Referrer-Policy',
        'Permissions-Policy',
        'Content-Security-Policy',
    ):
        assert f'add_header {header}' in nginx
    assert "script-src 'self' https://telegram.org" in nginx
    assert "client_max_body_size 1m;" in nginx
    assert "location = /api/v1/assets" in nginx
    assert "client_max_body_size 21m;" in nginx

    inner = (REPO_ROOT / 'backend' / 'deploy' / 'nginx.conf').read_text()
    assert "map $http_x_real_ip $auroom_real_ip" in inner
    assert inner.count("proxy_set_header X-Real-IP $auroom_real_ip;") >= 3
    assert "client_max_body_size 1m;" in inner
    assert "location = /api/v1/assets" in inner
    assert "limit_conn_zone $auroom_real_ip zone=auroom_upload_conn:10m;" in inner
    assert "limit_conn auroom_upload_conn 2;" in inner
    assert "limit_conn_status 429;" in inner


def test_frontend_shell_is_never_cached_but_hashed_assets_are_cacheable() -> None:
    nginx = (REPO_ROOT / 'frontend' / 'nginx.conf').read_text()

    assert 'location = /index.html' in nginx
    assert nginx.count('Cache-Control "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0"') >= 2
    assert 'Pragma "no-cache"' in nginx
    assert 'Cache-Control "public, max-age=604800"' in nginx


def test_supply_chain_dependencies_are_immutable_or_monitored() -> None:
    backend_docker = (REPO_ROOT / 'backend' / 'Dockerfile').read_text()
    renderer_docker = (REPO_ROOT / 'backend' / 'Dockerfile.renderer').read_text()
    frontend_docker = (REPO_ROOT / 'frontend' / 'Dockerfile').read_text()
    compose = (REPO_ROOT / 'backend' / 'docker-compose.yml').read_text()
    for content in (backend_docker, renderer_docker, frontend_docker):
        assert '@sha256:' in content
    assert compose.count('@sha256:') >= 3
    assert (REPO_ROOT / '.github' / 'dependabot.yml').exists()
    workflows = '\n'.join(path.read_text() for path in (REPO_ROOT / '.github' / 'workflows').glob('*.yml'))
    assert 'actions/checkout@v' not in workflows
    assert 'actions/setup-python@v' not in workflows
    assert 'actions/setup-node@v' not in workflows


def test_ci_has_dependency_and_container_build_gates() -> None:
    ci = (REPO_ROOT / '.github' / 'workflows' / 'ci.yml').read_text()
    assert 'pip-audit -r requirements.lock --require-hashes --progress-spinner off --strict' in ci
    assert 'pip-audit -r requirements-build.lock --require-hashes --progress-spinner off --strict' in ci
    assert 'npm audit --audit-level=high' in ci
    assert 'docker compose --project-directory backend -f backend/docker-compose.yml build api frontend' in ci
    deploy = (REPO_ROOT / 'ops' / 'deploy_docker.sh').read_text()
    assert 'Applying canonical host Nginx config' in deploy
    assert 'rollback_host_nginx' in deploy
    installer = (REPO_ROOT / 'ops' / 'install_host_nginx.sh').read_text()
    assert 'restore_previous' in installer
    assert 'Post-reload AuRoom health check failed' in installer


def test_compose_isolates_edge_and_data_planes() -> None:
    compose = (REPO_ROOT / 'backend' / 'docker-compose.yml').read_text()
    assert 'data:\n    internal: true' in compose
    assert 'security_opt:\n      - no-new-privileges:true' in compose
    assert 'cap_drop:\n      - ALL' in compose

    # Edge containers must not join the private data network.
    bot = compose.split('  bot:', 1)[1].split('\n\n  worker:', 1)[0]
    frontend = compose.split('  frontend:', 1)[1].split('\n  nginx:', 1)[0]
    nginx = compose.split('  nginx:', 1)[1].split('\n  postgres:', 1)[0]
    assert '- data' not in bot
    assert 'env_file:' not in bot
    assert 'RUNTIME_ROLE: "bot"' in bot
    for secret_name in (
        'DATABASE_URL',
        'REDIS_URL',
        'JWT_SECRET',
        'REFRESH_TOKEN_SECRET',
        'MEDIA_SIGNING_SECRET',
        'NEXUS_API_KEY',
        'YOOKASSA_SECRET_KEY',
    ):
        assert secret_name not in bot
    assert '- data' not in frontend
    assert '- data' not in nginx

    worker = compose.split('  worker:', 1)[1].split('\n\n  renderer-worker:', 1)[0]
    broadcast = compose.split('  broadcast-worker:', 1)[1].split('\n\n  maintenance:', 1)[0]
    maintenance = compose.split('  maintenance:', 1)[1].split('\n\n  frontend:', 1)[0]
    for service in (worker, broadcast, maintenance):
        assert 'env_file:' not in service
        assert 'JWT_SECRET' not in service
        assert 'REFRESH_TOKEN_SECRET' not in service
        assert 'YOOKASSA_SECRET_KEY' not in service
    assert 'NEXUS_API_KEY' in worker
    assert 'TELEGRAM_BOT_TOKEN' not in worker
    assert 'NEXUS_API_KEY' not in broadcast
    assert 'MEDIA_SIGNING_SECRET' not in broadcast
    assert 'TELEGRAM_BOT_TOKEN' in broadcast
    assert 'NEXUS_API_KEY' not in maintenance
    assert 'TELEGRAM_BOT_TOKEN' in maintenance
    assert 'MEDIA_SIGNING_SECRET' in maintenance

    postgres = compose.split('  postgres:', 1)[1].split('\n  redis:', 1)[0]
    redis = compose.split('  redis:', 1)[1].split('\nvolumes:', 1)[0]
    assert 'networks:\n      - data' in postgres
    assert 'networks:\n      - data' in redis
    assert 'POSTGRES_PASSWORD: "${POSTGRES_PASSWORD:-local-only-postgres-password-change-me}"' in postgres
    assert 'POSTGRES_PASSWORD: app' not in postgres
    assert 'REDIS_PASSWORD: "${REDIS_PASSWORD:-local-only-redis-password-change-me}"' in redis
    assert '--requirepass' in redis
    assert 'REDISCLI_AUTH=' in redis


def test_runtime_mutations_are_serialized_and_backups_are_private() -> None:
    deploy = (REPO_ROOT / 'ops' / 'deploy_docker.sh').read_text()
    backup = (REPO_ROOT / 'ops' / 'backup_runtime.sh').read_text()
    restore = (REPO_ROOT / 'ops' / 'restore_runtime.sh').read_text()
    housekeeping = (REPO_ROOT / 'ops' / 'runtime_housekeeping.sh').read_text()

    for script in (deploy, backup, restore, housekeeping):
        assert 'umask 077' in script
        assert '.runtime-mutation.lock' in script

    assert 'install -d -m 700' in backup
    assert 'chmod 600' in backup
    assert 'pg_restore --list' in backup
    assert 'tar -tzf' in backup
    assert 'Draining write traffic before database migrations' in deploy


def test_offsite_backup_is_encrypted_before_provider_upload() -> None:
    export = (REPO_ROOT / 'ops' / 'export_offsite_backup.sh').read_text()
    fetch = (REPO_ROOT / 'ops' / 'fetch_offsite_backup.sh').read_text()
    backup = (REPO_ROOT / 'ops' / 'backup_runtime.sh').read_text()
    monitor = (REPO_ROOT / 'ops' / 'runtime_monitor.sh').read_text()

    assert 'age --encrypt --recipient' in export
    assert '| age --encrypt' in export
    assert 'rclone copyto' in export
    assert '--immutable --checksum' in export
    assert 'OFFSITE_OK' in export
    assert 'AUROOM_BACKUP_AGE_IDENTITY_FILE' not in export

    assert 'AUROOM_BACKUP_AGE_IDENTITY_FILE' in fetch
    assert 'age --decrypt --identity' in fetch
    assert 'sha256sum' in fetch

    assert '.backup.env' in backup
    assert 'bash "${script_dir}/export_offsite_backup.sh"' in backup
    assert 'OFFSITE_OK' in monitor


def test_production_disables_fastapi_docs_and_openapi() -> None:
    env = os.environ.copy()
    env.update(
        {
            "APP_ENV": "production",
            "JWT_SECRET": "test-access-secret-abcdefghijklmnopqrstuvwxyz012345",
            "REFRESH_TOKEN_SECRET": "test-refresh-secret-abcdefghijklmnopqrstuvwxyz012345",
            "MEDIA_SIGNING_SECRET": "test-media-secret-abcdefghijklmnopqrstuvwxyz012345",
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app.main import app; "
                "assert app.openapi_url is None; "
                "assert app.docs_url is None; "
                "assert app.redoc_url is None"
            ),
        ],
        cwd=REPO_ROOT / "backend",
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr

def test_isolated_restore_drill_never_targets_live_runtime() -> None:
    drill = (REPO_ROOT / 'ops' / 'verify_restore_isolated.sh').read_text()

    assert 'docker run --rm -d' in drill
    assert '--network "container:${drill_name}"' in drill
    assert 'pg_restore -U app -d app --no-owner --no-privileges' in drill
    assert 'alembic upgrade head' in drill
    assert 'backup_manifest.py" verify' in drill
    assert 'tar -tzf' in drill
    assert 'docker stop "${drill_name}"' in drill

    # The drill must remain isolated from the live data path.
    assert 'DROP DATABASE' not in drill
    assert 'compose stop' not in drill
    assert 'restore_runtime.sh' not in drill
    assert '/data/media/*' not in drill
    assert 'docker volume rm' not in drill

def test_postgres_failure_probe_is_bounded_and_ci_exercises_recovery() -> None:
    probe = (REPO_ROOT / 'backend' / 'scripts' / 'postgres_failure_probe.py').read_text()
    ci = (REPO_ROOT / '.github' / 'workflows' / 'ci.yml').read_text()

    assert 'get_engine' in probe
    assert 'asyncio.wait_for' in probe
    assert 'dispose_engine' in probe
    assert 'SELECT 1' in probe
    assert 'DATABASE_URL' not in probe
    assert 'password' not in probe.lower()

    assert 'Controlled PostgreSQL pause/recovery probe' in ci
    assert 'docker pause auroom-chaos-postgres' in ci
    assert 'docker unpause auroom-chaos-postgres' in ci
    assert 'postgres_failure_probe.py expect-down 3' in ci
    assert 'postgres_failure_probe.py expect-up 2' in ci
    assert 'postgres_ready=0' in ci
    assert 'Chaos PostgreSQL TCP endpoint never became usable' in ci

