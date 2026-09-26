"""Real age encryption and offline storage exercise incremental disaster recovery."""
from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'ops'))
import backup_manifest
import telegram_backup as backup
from test_telegram_backup import FakeTelegram


@pytest.fixture
def keys(tmp_path):
    if not shutil.which('age'):
        pytest.skip('age required')
    identity = tmp_path / 'identity'
    subprocess.run(['age-keygen', '-o', str(identity)], check=True, capture_output=True)
    recipient = subprocess.check_output(['age-keygen', '-y', str(identity)], text=True).strip()
    return identity, recipient


def snapshot(root, number, files):
    path = root / f'20260927T{number:02d}0000Z'
    path.mkdir()
    (path / 'postgres.dump').write_bytes(f'database {number}'.encode())
    with tarfile.open(path / 'media.tar.gz', 'w:gz') as archive:
        for name, data in files.items():
            member = tarfile.TarInfo('./' + name)
            member.mode = 0o640
            member.mtime = number
            member.size = len(data)
            archive.addfile(member, BytesIO(data))
    backup_manifest.write_manifest(path)
    return path


def descriptor(path):
    return json.loads((path / '.telegram' / f'{path.name}.manifest.json').read_text())


def media_files(path):
    with tarfile.open(path / 'media.tar.gz') as archive:
        return {m.name.removeprefix('./'): archive.extractfile(m).read() for m in archive if m.isfile()}


@pytest.mark.parametrize('legacy', [False, True])
def test_new_image_uploads_only_delta_and_restores_without_old_local_snapshots(tmp_path, keys, legacy):
    identity, recipient = keys
    telegram = FakeTelegram()
    files = {'original.jpg': b'a' * 100_000, 'obsolete.jpg': b'old'}
    first = snapshot(tmp_path, 1, files)
    if legacy:
        backup.prepare(first, recipient)
    backup.export(first, recipient, telegram, [111, 222])
    assert descriptor(first)['version'] == (1 if legacy else 2)
    before = len(telegram.sent)
    files = {'original.jpg': b'a' * 100_000, 'added.jpg': b'new', 'modified.jpg': b'v1'}
    second = snapshot(tmp_path, 2, files)
    backup.export(second, recipient, telegram, [111, 222])
    manifest = descriptor(second)
    assert manifest['version'] == 3
    assert len(telegram.sent) - before == 6
    assert manifest['media']['base']['snapshot'] == first.name
    assert len(manifest['media']['deltas']) == 1
    assert 'original.jpg' not in json.dumps(manifest)
    third_files = {'original.jpg': files['original.jpg'], 'modified.jpg': b'v2', 'new/inside.jpg': b'inside'}
    third = snapshot(tmp_path, 3, third_files)
    backup.export(third, recipient, telegram, [111, 222])
    final_manifest = third / '.telegram' / f'{third.name}.manifest.json'
    shutil.rmtree(first)
    shutil.rmtree(second)
    restored = tmp_path / 'restored'
    backup.recover(final_manifest, restored, identity, telegram, None)
    assert media_files(restored) == third_files
    assert (restored / 'postgres.dump').read_bytes() == (third / 'postgres.dump').read_bytes()
    backup_manifest.verify(restored)
    assert (restored / 'SOURCE_SHA256SUMS').read_bytes() == (third / 'SHA256SUMS').read_bytes()


def all_parts(manifest):
    return manifest['parts'] + [p for c in backup.media_components(manifest) for p in c['parts']]


def test_overlay_compaction_reuses_baseline_and_manual_restore(tmp_path, keys, monkeypatch):
    identity, recipient = keys
    monkeypatch.setattr(backup.media_archives, 'MAX_DELTAS', 2)
    telegram = FakeTelegram()
    current = snapshot(tmp_path, 1, {'baseline': b'original'})
    backup.export(current, recipient, telegram, [111])
    baseline_ids = {p['file_id'] for p in descriptor(current)['media']['parts']}
    files = {'baseline': b'original'}
    earlier = [current]
    for number in range(2, 6):
        files[f'new{number}'] = str(number).encode()
        current = snapshot(tmp_path, number, files)
        before = len(telegram.sent)
        backup.export(current, recipient, telegram, [111])
        assert len(telegram.sent) - before == 3
        manifest = descriptor(current)
        assert {p['file_id'] for p in manifest['media']['base']['parts']} == baseline_ids
        assert len(manifest['media']['deltas']) <= 2
        if number == 4:
            assert len(manifest['media']['deltas']) == 1
        earlier.append(current)
    manual = tmp_path / 'manual'
    manual.mkdir()
    for part in all_parts(manifest):
        (manual / part['name']).write_bytes(telegram.files[part['file_id']])
    saved_manifest = tmp_path / 'manifest.json'
    saved_manifest.write_text(json.dumps(manifest))
    for old in earlier:
        shutil.rmtree(old)
    backup.recover(saved_manifest, tmp_path / 'restored', identity, None, manual)
    assert media_files(tmp_path / 'restored') == files
    backup_manifest.verify(tmp_path / 'restored')


def test_metadata_only_deletion_and_type_changes_preserve_final_inventory(tmp_path, keys):
    identity, recipient = keys
    telegram = FakeTelegram()
    first = snapshot(tmp_path, 1, {'same': b'keep', 'to-dir': b'old', 'to-file/child': b'remove'})
    backup.export(first, recipient, telegram, [111])
    second = snapshot(tmp_path, 2, {'same': b'keep', 'to-dir/child': b'new', 'to-file': b'file'})
    # Empty directory must survive even with no file content.
    with tarfile.open(second / 'media.tar.gz', 'r:gz') as source:
        entries = [(m, source.extractfile(m).read()) for m in source]
    with tarfile.open(second / 'media.tar.gz', 'w:gz') as output:
        for member, data in entries:
            member.mode = 0o600
            output.addfile(member, BytesIO(data))
        directory = tarfile.TarInfo('empty')
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o750
        directory.mtime = 25
        output.addfile(directory)
    backup_manifest.write_manifest(second)
    backup.export(second, recipient, telegram, [111])
    expected = backup.media_archives.inventory(second / 'media.tar.gz')
    backup.recover(second / '.telegram' / f'{second.name}.manifest.json', tmp_path / 'out', identity, telegram, None)
    assert backup.media_archives.inventory(tmp_path / 'out/media.tar.gz') == expected
    # Same bytes, changed mtime, and deletion require only DB + final index.
    third = snapshot(tmp_path, 3, {'same': b'keep'})
    before = len(telegram.sent)
    backup.export(third, recipient, telegram, [111])
    assert len(telegram.sent) - before == 2
    assert len(descriptor(third)['media']['deltas']) == 1
    backup.recover(third / '.telegram' / f'{third.name}.manifest.json', tmp_path / 'out3', identity, telegram, None)
    assert media_files(tmp_path / 'out3') == {'same': b'keep'}


def test_incremental_reused_part_failure_and_partial_delivery_resume(tmp_path, keys):
    _, recipient = keys
    telegram = FakeTelegram()
    first = snapshot(tmp_path, 1, {'old': b'old'})
    backup.export(first, recipient, telegram, [111, 222])
    part = descriptor(first)['media']['parts'][0]
    original = telegram.files[part['file_id']]
    telegram.files[part['file_id']] = b'broken'
    second = snapshot(tmp_path, 2, {'old': b'old', 'new': b'new'})
    with pytest.raises(AssertionError):
        backup.export(second, recipient, telegram, [111, 222])
    assert not (second / 'OFFSITE_OK').exists()
    before = list(telegram.sent)
    telegram.files[part['file_id']] = original
    telegram.fail_chat = 222
    with pytest.raises(ValueError):
        backup.export(second, recipient, telegram, [111, 222])
    assert not (second / 'OFFSITE_OK').exists()
    telegram.fail_chat = None
    backup.export(second, recipient, telegram, [111, 222])
    for sent in before:
        assert telegram.sent.count(sent) == 1
    assert (second / 'OFFSITE_OK').exists()


@pytest.mark.parametrize('mutation', ['index_hash', 'missing_delta', 'duplicate_delta', 'wrong_database'])
def test_incremental_manifest_and_content_tampering_fails(tmp_path, keys, mutation):
    identity, recipient = keys
    telegram = FakeTelegram()
    first = snapshot(tmp_path, 1, {'old': b'old'})
    backup.export(first, recipient, telegram, [111])
    second = snapshot(tmp_path, 2, {'old': b'old', 'new': b'new'})
    backup.export(second, recipient, telegram, [111])
    manifest = descriptor(second)
    if mutation == 'index_hash':
        manifest['index_sha256'] = '0' * 64
    elif mutation == 'missing_delta':
        manifest['media']['deltas'] = []
    elif mutation == 'duplicate_delta':
        manifest['media']['deltas'] *= 2
    else:
        state = json.loads((second / '.telegram/media-index.json').read_text())
        state['database_sha256'] = '0' * 64
        backup.save_json(second / '.telegram/media-index.json', state)
        payload = tmp_path / 'payload' / second.name
        payload.mkdir(parents=True)
        for name in ('postgres.dump', 'SHA256SUMS'):
            shutil.copyfile(second / name, payload / name)
        shutil.copyfile(second / '.telegram/media-index.json', payload / 'media-index.json')
        component = backup.pack_component(payload, recipient, payload, 'database-v3',
                                          ('postgres.dump', 'SHA256SUMS', 'media-index.json'))
        for part in component['parts']:
            part['file_id'] = 'tampered-' + part['name']
            telegram.files[part['file_id']] = (payload / part['name']).read_bytes()
        manifest['parts'] = component['parts']
        manifest['index_sha256'] = backup.digest(payload / 'media-index.json')
    path = tmp_path / 'bad.json'
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        backup.recover(path, tmp_path / 'bad-out', identity, telegram, None)
    assert not (tmp_path / 'bad-out/SOURCE_SHA256SUMS').exists()


@pytest.mark.parametrize('kind', ['parent', 'absolute', 'duplicate', 'symlink', 'hardlink', 'fifo', 'parent_file'])
def test_unsafe_media_members_rejected(tmp_path, kind):
    path = tmp_path / 'unsafe.tar.gz'
    with tarfile.open(path, 'w:gz') as tar:
        first = tarfile.TarInfo('../escape' if kind == 'parent' else '/escape' if kind == 'absolute' else 'a')
        if kind in ('symlink', 'hardlink', 'fifo'):
            first.type = {'symlink': tarfile.SYMTYPE, 'hardlink': tarfile.LNKTYPE, 'fifo': tarfile.FIFOTYPE}[kind]
            first.linkname = '../escape'
        tar.addfile(first, BytesIO())
        if kind in ('duplicate', 'parent_file'):
            tar.addfile(tarfile.TarInfo('./a' if kind == 'duplicate' else 'a/child'), BytesIO())
    with pytest.raises(ValueError):
        backup.media_archives.inventory(path)


def test_source_change_after_preparation_cannot_resume(tmp_path, keys):
    _, recipient = keys
    telegram = FakeTelegram()
    first = snapshot(tmp_path, 1, {'old': b'old'})
    backup.export(first, recipient, telegram, [111])
    second = snapshot(tmp_path, 2, {'new': b'new'})
    backup.prepare_incremental(second, recipient, [111])
    (second / 'postgres.dump').write_bytes(b'changed')
    backup_manifest.write_manifest(second)
    with pytest.raises(ValueError, match='Snapshot changed'):
        backup.export(second, recipient, telegram, [111])
    assert not (second / 'OFFSITE_OK').exists()
