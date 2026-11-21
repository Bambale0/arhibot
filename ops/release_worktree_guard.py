#!/usr/bin/env python3
"""Reject deployments over dirty or incorrectly targeted checkout trees.

The deployment script separately runs an rsync --delete dry-run because Git
cannot see ignored host-owned files. Both checks must pass before mutation.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# These are explicitly protected by the matching rsync exclusion list.
PROTECTED = (
    "backups",
    ".release",
    "backend/.env",
    ".backup.env",
    ".runtime-monitor",
    ".runtime-mutation.lock",
)


def is_clean_checkout(path: Path) -> bool:
    repo = path.resolve()
    try:
        top = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
        ).stdout.strip()
        if Path(top).resolve() != repo:
            return False
        output = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
                "--",
                ".",
                *(f":(exclude){item}" for item in PROTECTED),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return False
    return not output


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not is_clean_checkout(Path(argv[1])):
        print(
            "Release checkout guard: REFUSED (dirty checkout, nested directory or invalid Git root)",
            file=sys.stderr,
        )
        return 1
    print("Release checkout guard: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
