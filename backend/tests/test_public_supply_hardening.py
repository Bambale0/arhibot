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
    assert 'npm audit --omit=dev --audit-level=high' in ci
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
    frontend = compose.split('  frontend:', 1)[1].split('\n  nginx:', 1)[0]
    nginx = compose.split('  nginx:', 1)[1].split('\n  postgres:', 1)[0]
    assert '- data' not in frontend
    assert '- data' not in nginx

    postgres = compose.split('  postgres:', 1)[1].split('\n  redis:', 1)[0]
    redis = compose.split('  redis:', 1)[1].split('\nvolumes:', 1)[0]
    assert 'networks:\n      - data' in postgres
    assert 'networks:\n      - data' in redis


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
