from __future__ import annotations

import tomllib
from pathlib import Path

from app.core.config import Settings
from app.main import app
from app.version import __version__

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_application_version_has_single_source(monkeypatch) -> None:
    monkeypatch.setenv('APP_VERSION', '9.9.9')
    settings = Settings(_env_file=None)
    assert not hasattr(settings, 'app_version')
    assert app.version == __version__


def test_package_version_is_loaded_from_app_version_module() -> None:
    pyproject = tomllib.loads((REPO_ROOT / 'backend' / 'pyproject.toml').read_text())
    assert pyproject['project']['dynamic'] == ['version']
    assert pyproject['tool']['hatch']['version']['path'] == 'app/version.py'
    assert __version__ == '0.6.0'


def test_runtime_env_cannot_override_application_version() -> None:
    example = (REPO_ROOT / 'backend' / '.env.example').read_text()
    assert 'APP_VERSION=' not in example


def test_uvicorn_access_log_is_disabled_because_structured_middleware_logs_http() -> None:
    dockerfile = (REPO_ROOT / 'backend' / 'Dockerfile').read_text()
    assert '--no-access-log' in dockerfile
