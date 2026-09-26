#!/usr/bin/env python3
"""Portable backup checksums; legacy absolute entries are mapped to approved local files."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path, PurePosixPath

FILES = ('postgres.dump', 'media.tar.gz')


def digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'Backup entry must be a regular local file: {path.name}')
    with path.open('rb') as stream:
        result = hashlib.sha256()
        while block := stream.read(1024 * 1024):
            result.update(block)
        return result.hexdigest()


def write_manifest(directory: Path) -> None:
    text = ''.join(f'{digest(directory / name)}  {name}\n' for name in FILES)
    path = directory / 'SHA256SUMS'
    if path.is_symlink():
        raise ValueError('Manifest must not be a symlink')
    path.write_text(text, encoding='utf-8')
    path.chmod(0o600)


def verify(directory: Path) -> None:
    manifest = directory / 'SHA256SUMS'
    if manifest.is_symlink() or manifest.stat().st_size > 16384:
        raise ValueError('Invalid backup manifest')
    seen = set()
    for line in manifest.read_text(encoding='utf-8').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64}) [ *](.+)', line)
        if not match:
            raise ValueError('Invalid checksum record')
        expected, raw = match.groups()
        path = PurePosixPath(raw)
        name = path.name
        # Only old absolute paths or new flat relative names are accepted.
        if '..' in path.parts or (not path.is_absolute() and raw != name):
            raise ValueError('Unsafe checksum path')
        if name not in FILES or name in seen:
            raise ValueError('Unexpected or duplicate backup entry')
        seen.add(name)
        if digest(directory / name) != expected:
            raise ValueError(f'Backup checksum mismatch: {name}')
    if seen != set(FILES):
        raise ValueError('Incomplete backup manifest')


if __name__ == '__main__':
    try:
        command, directory = sys.argv[1:]
        if command not in {'write', 'verify'}:
            raise ValueError('Use write or verify')
        (write_manifest if command == 'write' else verify)(Path(directory))
    except (ValueError, OSError) as exc:
        sys.exit(str(exc))
