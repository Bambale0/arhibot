"""Test the deployment safety guard without accessing a production server."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GUARD = Path(__file__).resolve().parents[2] / "ops" / "release_worktree_guard.py"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


class ReleaseWorktreeGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.repo = Path(self.workspace.name) / "project"
        self.repo.mkdir()
        _git(self.repo, "init", "-q")
        (self.repo / "app.py").write_text("print('ok')\n", encoding="utf-8")
        _git(self.repo, "add", "app.py")
        _git(self.repo, "-c", "user.name=CI", "-c", "user.email=ci@example.test", "commit", "-qm", "initial")

    def run_guard(self, repo: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(GUARD), str(repo or self.repo)],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_clean_checkout_passes(self) -> None:
        self.assertEqual(self.run_guard().returncode, 0)

    def test_protected_runtime_paths_are_excluded(self) -> None:
        for folder, filename in (
            (".release", "candidate.tgz"),
            ("backups", "backup.manifest"),
            ("backend", ".env"),
            (".runtime-monitor", "state.json"),
        ):
            dest = self.repo / folder
            dest.mkdir(exist_ok=True)
            (dest / filename).write_text("local-only", encoding="utf-8")
        self.assertEqual(self.run_guard().returncode, 0)

    def test_modified_tracked_file_blocks(self) -> None:
        (self.repo / "app.py").write_text("modified", encoding="utf-8")
        self.assertEqual(self.run_guard().returncode, 1)

    def test_untracked_file_blocks(self) -> None:
        (self.repo / "customer-data.txt").write_text("preserve", encoding="utf-8")
        self.assertEqual(self.run_guard().returncode, 1)

    def test_wrong_git_root_blocks(self) -> None:
        nested = self.repo / "nested"
        nested.mkdir()
        self.assertEqual(self.run_guard(nested).returncode, 1)
        self.assertEqual(self.run_guard(Path(self.workspace.name)).returncode, 1)

    def test_rsync_dry_run_reports_deletion_without_deleting(self) -> None:
        if not shutil.which("rsync"):
            self.skipTest("rsync is not installed")
        candidate = Path(self.workspace.name) / "candidate"
        target = Path(self.workspace.name) / "target"
        candidate.mkdir()
        target.mkdir()
        protected = target / "customer-media"
        protected.write_text("must survive", encoding="utf-8")
        result = subprocess.run(
            [
                "rsync", "--archive", "--delete", "--dry-run", "--itemize-changes",
                f"{candidate}/", f"{target}/",
            ],
            check=True, capture_output=True, text=True,
        )
        self.assertIn("*deleting", result.stdout)
        self.assertTrue(protected.exists())

    def test_release_gate_is_before_destructive_rsync(self) -> None:
        source = (GUARD.parent / "deploy_docker.sh").read_text(encoding="utf-8")
        self.assertIn("release_worktree_guard.py", source)
        self.assertIn("rsync --archive --delete --dry-run", source)
        self.assertIn("Refusing deploy: runtime DB/media backups disabled", source)
        self.assertLess(source.index("release_worktree_guard.py"), source.index("mutation_started=1"))


if __name__ == "__main__":
    unittest.main()
