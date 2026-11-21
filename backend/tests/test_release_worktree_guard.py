"""Regression tests for the host checkout safety gate before deploy."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parents[2] / "ops" / "release_worktree_guard.py"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    target = tmp_path / "project"
    target.mkdir()
    _git(target, "init", "-q")
    (target / "app.py").write_text("print('ok')\n", encoding="utf-8")
    _git(target, "add", "app.py")
    _git(target, "-c", "user.name=CI", "-c", "user.email=ci@example.test", "commit", "-qm", "initial")
    return target


def _guard(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(GUARD), str(repo)], capture_output=True, text=True, timeout=10)


def test_clean_checkout_accepted(repo: Path) -> None:
    assert _guard(repo).returncode == 0


def test_protected_runtime_locations_do_not_fail_guard(repo: Path) -> None:
    for folder, filename in (
        (".release", "candidate.tgz"),
        ("backups", "backup.manifest"),
        ("backend", ".env"),
        (".runtime-monitor", "state.json"),
    ):
        p = repo / folder
        p.mkdir(exist_ok=True)
        (p / filename).write_text("local-only", encoding="utf-8")
    assert _guard(repo).returncode == 0


def test_modified_tracked_file_blocks_deploy(repo: Path) -> None:
    (repo / "app.py").write_text("modified", encoding="utf-8")
    assert _guard(repo).returncode == 1


def test_untracked_file_blocks_deploy(repo: Path) -> None:
    (repo / "customer-data.txt").write_text("preserve", encoding="utf-8")
    assert _guard(repo).returncode == 1


def test_nested_path_and_non_git_directory_are_rejected(repo: Path, tmp_path: Path) -> None:
    nested = repo / "nested"
    nested.mkdir()
    assert _guard(nested).returncode == 1
    assert _guard(tmp_path).returncode == 1


def test_deploy_script_fails_closed_before_rsync() -> None:
    script = (GUARD.parent / "deploy_docker.sh").read_text(encoding="utf-8")
    assert "release_worktree_guard.py" in script
    assert "rsync --archive --delete --dry-run" in script
    assert "Refusing deploy: rsync would delete host files" in script
    assert "Refusing deploy: runtime DB/media backups disabled" in script
    assert script.index("release_worktree_guard.py") < script.index("mutation_started=1")
