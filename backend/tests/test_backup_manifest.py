import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('backup_manifest', Path(__file__).resolve().parents[2] / 'ops/backup_manifest.py')
manifest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manifest)


def snapshot(path):
    path.mkdir()
    for name in manifest.FILES:
        (path / name).write_bytes(name.encode())
    manifest.write_manifest(path)
    return path


@pytest.mark.parametrize('legacy', [False, True])
def test_relocated_backup_checks_copied_bytes(tmp_path, legacy):
    import shutil
    original = snapshot(tmp_path / 'original')
    if legacy:
        p = original / 'SHA256SUMS'
        p.write_text(''.join(f'{manifest.digest(original / n)}  {original / n}\n' for n in manifest.FILES))
    moved = tmp_path / 'moved'
    shutil.copytree(original, moved)
    manifest.verify(moved)
    (moved / 'postgres.dump').write_bytes(b'tampered')
    with pytest.raises(ValueError, match='checksum mismatch'):
        manifest.verify(moved)
    shutil.copyfile(original / 'postgres.dump', moved / 'postgres.dump')
    original.rename(tmp_path / 'unavailable')
    manifest.verify(moved)


@pytest.mark.parametrize('entry', ['../postgres.dump', 'sub/postgres.dump', '/old/../postgres.dump', 'other.dump'])
def test_unsafe_backup_manifest_rejected(tmp_path, entry):
    path = snapshot(tmp_path / 'snapshot')
    text = (path / 'SHA256SUMS').read_text().replace('  postgres.dump', f'  {entry}')
    (path / 'SHA256SUMS').write_text(text)
    with pytest.raises(ValueError):
        manifest.verify(path)


def test_symlink_and_missing_checksum_rejected(tmp_path):
    path = snapshot(tmp_path / 'snapshot')
    dump = path / 'postgres.dump'
    dump.rename(tmp_path / 'external')
    dump.symlink_to(tmp_path / 'external')
    with pytest.raises(ValueError):
        manifest.verify(path)
    (path / 'SHA256SUMS').write_text('')
    with pytest.raises(ValueError):
        manifest.verify(path)
