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
    assert 'pip-audit . --progress-spinner off --strict' in ci
    assert 'npm audit --omit=dev --audit-level=high' in ci
    assert 'docker compose --project-directory backend -f backend/docker-compose.yml build api frontend' in ci
    deploy = (REPO_ROOT / 'ops' / 'deploy_docker.sh').read_text()
    assert 'Applying canonical host Nginx config' in deploy
    assert 'rollback_host_nginx' in deploy
    installer = (REPO_ROOT / 'ops' / 'install_host_nginx.sh').read_text()
    assert 'restore_previous' in installer
    assert 'Post-reload AuRoom health check failed' in installer


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
