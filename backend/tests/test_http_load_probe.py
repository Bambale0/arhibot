from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE = REPO_ROOT / "backend" / "scripts" / "http_load_probe.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AUROOM_LOAD_TOKEN"] = "test-token"
    return subprocess.run(
        [sys.executable, str(PROBE), *args],
        cwd=REPO_ROOT / "backend",
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_load_probe_refuses_remote_target_without_explicit_opt_in() -> None:
    result = _run(
        "--base-url",
        "https://example.test/api/v1",
        "--requests",
        "1",
        "--concurrency",
        "1",
    )
    assert result.returncode == 2
    assert "Refusing a remote load target" in result.stderr


def test_load_probe_requires_second_opt_in_for_remote_writes() -> None:
    result = _run(
        "--base-url",
        "https://example.test/api/v1",
        "--mode",
        "project-write",
        "--requests",
        "1",
        "--concurrency",
        "1",
        "--allow-remote",
    )
    assert result.returncode == 2
    assert "Refusing remote writes" in result.stderr


def test_load_probe_scope_excludes_provider_and_financial_writes() -> None:
    content = PROBE.read_text()
    assert '"/projects"' in content
    assert '"/me"' in content
    assert "/generations" not in content
    assert "/billing" not in content
    assert "/broadcast" not in content
    assert "AUROOM_LOAD_TOKEN" in content


def test_ci_runs_authenticated_read_and_project_write_load() -> None:
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "Bounded authenticated HTTP load probe" in ci
    assert "python -m uvicorn app.main:app" in ci
    assert "--mode read" in ci
    assert "--mode project-write" in ci
    assert "--max-error-rate 0" in ci
