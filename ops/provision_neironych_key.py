#!/usr/bin/env python3
"""Owner-triggered dev secret provisioning. Read key from stdin, never print it."""
from __future__ import annotations

import os
from pathlib import Path
import re
import stat
import sys
import tempfile


def provision(path: Path, key: str) -> None:
    # Deliberately conservative: reject whitespace, interpolation and dotenv
    # metacharacters instead of altering the credential or risking expansion.
    if not re.fullmatch(r"[A-Za-z0-9_.~+/:=-]{8,1024}", key):
        raise ValueError("Secret is empty or has an unsupported format; existing configuration unchanged")
    if path.is_symlink() or not path.is_file():
        raise ValueError("Existing dev environment file is required")
    info = path.stat()
    if info.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ValueError("Existing dev environment file must already be owner-only")
    text = path.read_text()
    lines = text.splitlines(keepends=True)
    kept = [line for line in lines if not re.match(r"^\s*(?:export\s+)?NEIRONYCH_API_KEY\s*=", line)]
    output = "".join(kept)
    if output and not output.endswith("\n"):
        output += "\n"
    output += f"NEIRONYCH_API_KEY='{key}'\n"
    fd, temporary = tempfile.mkstemp(prefix=".neironych-env-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), stat.S_IMODE(info.st_mode))
            os.fchown(stream.fileno(), info.st_uid, info.st_gid)
            stream.write(output)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    if len(sys.argv) != 2:
        print("Expected dev environment file path", file=sys.stderr)
        return 2
    try:
        provision(Path(sys.argv[1]), sys.stdin.read(1025))
    except (ValueError, OSError):
        print("Neironych key provisioning failed; inspect configuration and permissions locally", file=sys.stderr)
        return 1
    print("Neironych development key configured (value not displayed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
