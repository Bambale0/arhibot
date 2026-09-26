"""Safe content-indexed media archives; no archive member is extracted by pathname."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path, PurePosixPath
import re
import tarfile

from backup_manifest import digest

MAX_ENTRIES = 100_000
MAX_DELTAS = 8


def safe_name(raw: str) -> str:
    if not isinstance(raw, str) or not raw or any(ord(c) < 32 for c in raw) or '\\' in raw:
        raise ValueError('Unsafe media path')
    path = PurePosixPath(raw)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Unsafe media path')
    return str(path)


def validate_index(index: dict) -> None:
    if not isinstance(index, dict) or len(index) > MAX_ENTRIES:
        raise ValueError('Invalid media index')
    for name, item in index.items():
        if safe_name(name) != name or not isinstance(item, dict):
            raise ValueError('Invalid media index path')
        if item.get('kind') not in ('file', 'directory'):
            raise ValueError('Invalid media entry type')
        if type(item.get('mode')) is not int or not 0 <= item['mode'] <= 0o777:
            raise ValueError('Invalid media mode')
        if type(item.get('mtime')) not in (int, float) or not math.isfinite(item['mtime']):
            raise ValueError('Invalid media timestamp')
        if item['kind'] == 'file':
            if name == '.' or type(item.get('size')) is not int or item['size'] < 0:
                raise ValueError('Invalid media file size')
            if not isinstance(item.get('sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', item['sha256']):
                raise ValueError('Invalid media file checksum')
        for parent in PurePosixPath(name).parents:
            if str(parent) in index and index[str(parent)].get('kind') != 'directory':
                raise ValueError('Media file conflicts with a parent directory')


def cache_path(directory: Path, name: str) -> Path:
    return directory / hashlib.sha256(name.encode()).hexdigest()


def inventory(archive: Path, *, wanted: dict | None = None, cache: Path | None = None) -> dict:
    """Hash every member; optionally retain only bytes matching the final index."""
    entries = {}
    with tarfile.open(archive, 'r|gz') as tar:
        for member in tar:
            name = safe_name(member.name)
            if name in entries or len(entries) >= MAX_ENTRIES or not (member.isfile() or member.isdir()):
                raise ValueError('Unsafe or duplicate media archive member')
            item = {'kind': 'file' if member.isfile() else 'directory',
                    'mode': member.mode & 0o777, 'mtime': member.mtime}
            if member.isfile():
                expected = (wanted or {}).get(name, {})
                retain = cache is not None and expected.get('kind') == 'file' and expected['size'] == member.size
                temporary = cache / 'incoming' if retain else None
                output = temporary.open('wb') if temporary else None
                checksum = hashlib.sha256()
                count = 0
                try:
                    with tar.extractfile(member) as source:
                        while block := source.read(1024 * 1024):
                            count += len(block)
                            checksum.update(block)
                            if output:
                                output.write(block)
                finally:
                    if output:
                        output.close()
                if count != member.size:
                    raise ValueError('Truncated media file')
                item.update(size=count, sha256=checksum.hexdigest())
                if temporary:
                    if expected['sha256'] == item['sha256']:
                        temporary.replace(cache_path(cache, name))
                    else:
                        temporary.unlink()
            entries[name] = item
    validate_index(entries)
    return entries


def changed_files(current: dict, previous: dict) -> set[str]:
    return {name for name, item in current.items() if item['kind'] == 'file'
            and (previous.get(name, {}).get('kind') != 'file'
                 or previous[name].get('sha256') != item['sha256'])}


def tar_info(name: str, item: dict) -> tarfile.TarInfo:
    entry = tarfile.TarInfo(name)
    entry.mode, entry.mtime = item['mode'], item['mtime']
    entry.type = tarfile.REGTYPE if item['kind'] == 'file' else tarfile.DIRTYPE
    entry.size = item.get('size', 0)
    return entry


def make_delta(source: Path, target: Path, current: dict, names: set[str]) -> None:
    seen = set()
    with tarfile.open(source, 'r|gz') as original, tarfile.open(target, 'w:gz') as output:
        for member in original:
            name = safe_name(member.name)
            if name not in names:
                continue
            if name in seen or not member.isfile():
                raise ValueError('Media source changed while packing')
            seen.add(name)
            with original.extractfile(member) as stream:
                output.addfile(tar_info(name, current[name]), stream)
    if seen != names or inventory(target) != {name: current[name] for name in names}:
        raise ValueError('Media source changed while packing')


def assemble(target: Path, index: dict, cache: Path) -> None:
    validate_index(index)
    # Check all bytes before creating an archive or replacement checksums.
    for name, item in index.items():
        if item['kind'] != 'file':
            continue
        path = cache_path(cache, name)
        if not path.is_file() or path.stat().st_size != item['size']:
            raise ValueError('Missing final media content')
        if digest(path) != item['sha256']:
            raise ValueError('Final media checksum mismatch')
    with tarfile.open(target, 'w:gz') as output:
        for name, item in sorted(index.items()):
            entry = tar_info(name, item)
            if item['kind'] == 'file':
                with cache_path(cache, name).open('rb') as stream:
                    output.addfile(entry, stream)
            else:
                output.addfile(entry)
    if inventory(target) != index:
        raise ValueError('Reconstructed media index mismatch')
