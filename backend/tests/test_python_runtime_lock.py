from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_runtime_lock_is_hash_locked_and_used_by_images() -> None:
    lock = (REPO_ROOT / 'backend' / 'requirements.lock').read_text()
    build_lock = (REPO_ROOT / 'backend' / 'requirements-build.lock').read_text()
    assert '--hash=sha256:' in lock
    assert 'alembic==' in lock
    assert 'fastapi==' in lock
    assert 'sqlalchemy==' in lock
    assert 'hatchling==' in build_lock
    assert '--hash=sha256:' in build_lock

    for relative in ('backend/Dockerfile', 'backend/Dockerfile.renderer'):
        dockerfile = (REPO_ROOT / relative).read_text()
        assert 'COPY requirements-build.lock ./' in dockerfile
        assert 'pip install --require-hashes -r requirements-build.lock' in dockerfile
        assert 'pip wheel --no-deps --no-build-isolation' in dockerfile
        assert 'COPY requirements.lock ./' in dockerfile
        assert 'pip install --require-hashes -r requirements.lock' in dockerfile
        assert 'pip install --no-deps /tmp/ai_architecture_backend-*.whl' in dockerfile
        assert 'pip install --upgrade pip' not in dockerfile


def test_ci_regenerates_and_audits_the_lock() -> None:
    ci = (REPO_ROOT / '.github' / 'workflows' / 'ci.yml').read_text()
    lock_script = (REPO_ROOT / 'backend' / 'scripts' / 'dependency_locks.sh').read_text()
    assert 'Verify Python dependency locks are current' in ci
    assert './scripts/dependency_locks.sh CHECK' in ci
    assert '--no-header' in lock_script
    assert '--build-deps-for=wheel' in lock_script
    assert 'cmp requirements.lock' in lock_script
    assert 'cmp requirements-build.lock' in lock_script
    assert 'pip-audit -r requirements.lock --require-hashes' in ci
    assert 'pip-audit -r requirements-build.lock --require-hashes' in ci


def test_lock_tool_version_is_pinned() -> None:
    pyproject = (REPO_ROOT / 'backend' / 'pyproject.toml').read_text()
    assert 'pip-tools==7.6.1' in pyproject
    assert 'requires = ["hatchling==1.32.0"]' in pyproject
