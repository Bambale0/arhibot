import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

OPS = Path(__file__).resolve().parents[2] / 'ops'
sys.path.insert(0, str(OPS))
import telegram_backup as backup
import backup_manifest


class FakeTelegram:
    def __init__(self):
        self.files = {}
        self.sent = []
        self.fail_chat = None

    def call(self, method, fields, document=None):
        assert method == 'sendDocument'
        if fields['chat_id'] == self.fail_chat:
            raise ValueError('simulated unavailable administrator')
        self.sent.append((fields['chat_id'], document.name if document else fields['document']))
        if document:
            file_id = f'file-{len(self.files)}'
            self.files[file_id] = document.read_bytes()
        else:
            file_id = fields['document']
        return {'document': {'file_id': file_id}, 'message_id': len(self.sent)}

    def download(self, file_id, target, expected_hash, expected_size):
        content = self.files[file_id]
        assert len(content) == expected_size
        assert backup.hashlib.sha256(content).hexdigest() == expected_hash
        target.write_bytes(content)


@pytest.fixture
def encrypted_snapshot(tmp_path, monkeypatch):
    if not shutil.which('age'):
        pytest.skip('age is required for encryption/recovery integration')
    identity = tmp_path / 'identity.txt'
    subprocess.run(['age-keygen', '-o', str(identity)], check=True, capture_output=True)
    recipient = subprocess.check_output(['age-keygen', '-y', str(identity)], text=True).strip()
    snapshot = tmp_path / '20260922T120000Z'
    snapshot.mkdir()
    (snapshot / 'postgres.dump').write_bytes(b'isolated database fixture')
    (snapshot / 'media.tar.gz').write_bytes(b'isolated media fixture')
    backup_manifest.write_manifest(snapshot)
    monkeypatch.setattr(backup, 'CHUNK_SIZE', 2048)
    return snapshot, identity, recipient


@pytest.mark.parametrize('legacy', [False, True])
def test_encrypted_admin_delivery_download_and_restore(encrypted_snapshot, tmp_path, legacy):
    snapshot, identity, recipient = encrypted_snapshot
    telegram = FakeTelegram()
    if legacy:
        backup.prepare(snapshot, recipient)
    backup.export(snapshot, recipient, telegram, [111, 222])
    assert (snapshot / 'OFFSITE_OK').exists()
    assert set(chat for chat, _ in telegram.sent) == {111, 222}
    manifest = snapshot / '.telegram' / f'{snapshot.name}.manifest.json'
    recovered = tmp_path / 'recovered'
    backup.recover(manifest, recovered, identity, telegram, None)
    for name in backup_manifest.FILES:
        assert (recovered / name).read_bytes() == (snapshot / name).read_bytes()
    # Independently usable after loss of the bot token: manually downloaded pieces.
    backup.recover(manifest, tmp_path / 'manual', identity, None, snapshot / '.telegram')
    before = len(telegram.sent)
    backup.export(snapshot, recipient, telegram, [111, 222])
    assert len(telegram.sent) == before


@pytest.mark.parametrize('legacy', [False, True])
def test_partial_delivery_never_marks_success_and_resumes(encrypted_snapshot, legacy):
    snapshot, _, recipient = encrypted_snapshot
    telegram = FakeTelegram()
    if legacy:
        backup.prepare(snapshot, recipient)
    telegram.fail_chat = 222
    with pytest.raises(ValueError):
        backup.export(snapshot, recipient, telegram, [111, 222])
    assert not (snapshot / 'OFFSITE_OK').exists()
    sent_before = list(telegram.sent)
    telegram.fail_chat = None
    backup.export(snapshot, recipient, telegram, [111, 222])
    assert telegram.sent.count(sent_before[0]) == 1
    assert (snapshot / 'OFFSITE_OK').exists()


def test_corrupt_downloaded_parts_rejected(encrypted_snapshot, tmp_path):
    snapshot, identity, recipient = encrypted_snapshot
    directory, state = backup.prepare(snapshot, recipient)
    manifest = directory / 'manifest.json'
    backup.save_json(manifest, state)
    (directory / state['parts'][0]['name']).write_bytes(b'corrupt')
    with pytest.raises(ValueError):
        backup.recover(manifest, tmp_path / 'recovered', identity, None, directory)


@pytest.mark.parametrize('recipients', [[], [-100123], [0]])
def test_export_requires_private_admin_recipients(tmp_path, recipients):
    with pytest.raises(ValueError, match='administrator'):
        backup.export(tmp_path, 'unused', FakeTelegram(), recipients)


def test_manifest_path_traversal_rejected(tmp_path):
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps({'version': 1, 'snapshot': '20260922T120000Z', 'parts': [
        {'name': '../escape', 'size': 1, 'sha256': '0' * 64},
    ]}))
    with pytest.raises(ValueError, match='part name'):
        backup.recover(path, tmp_path / 'out', tmp_path / 'identity', None, tmp_path)


def next_snapshot(snapshot, name, database=b'new database', media=None):
    target = snapshot.parent / name
    target.mkdir()
    (target / 'postgres.dump').write_bytes(database)
    (target / 'media.tar.gz').write_bytes(media if media is not None else (snapshot / 'media.tar.gz').read_bytes())
    backup_manifest.write_manifest(target)
    return target


def test_legacy_media_reused_without_resending_and_restores_fresh_database(encrypted_snapshot, tmp_path):
    original, identity, recipient = encrypted_snapshot
    telegram = FakeTelegram()
    # Explicitly prepare v1 to prove upgrade compatibility with existing snapshots.
    backup.prepare(original, recipient)
    backup.export(original, recipient, telegram, [111, 222])
    old_names = {name for _, name in telegram.sent}
    sent_before = len(telegram.sent)
    current = next_snapshot(original, '20260922T130000Z')
    backup.export(current, recipient, telegram, [111, 222])
    manifest = current / '.telegram' / f'{current.name}.manifest.json'
    descriptor = json.loads(manifest.read_text())
    assert descriptor['version'] == 2
    assert descriptor['media']['kind'] == 'legacy-v1-bundle'
    assert all(name not in old_names for _, name in telegram.sent[sent_before:])
    assert len(telegram.sent) - sent_before == 2 * (len(descriptor['parts']) + 1)
    shutil.rmtree(original)
    backup.recover(manifest, tmp_path / 'restored', identity, telegram, None)
    for name in backup_manifest.FILES:
        assert (tmp_path / 'restored' / name).read_bytes() == (current / name).read_bytes()


def test_v2_reuse_is_flat_and_manual_restore_survives_local_retention(encrypted_snapshot, tmp_path):
    original, identity, recipient = encrypted_snapshot
    telegram = FakeTelegram()
    backup.export(original, recipient, telegram, [111])
    middle = next_snapshot(original, '20260922T130000Z', database=b'middle db')
    backup.export(middle, recipient, telegram, [111])
    latest = next_snapshot(middle, '20260922T140000Z', database=b'latest db')
    before = len(telegram.sent)
    backup.export(latest, recipient, telegram, [111])
    manifest = latest / '.telegram' / f'{latest.name}.manifest.json'
    state = json.loads(manifest.read_text())
    assert state['version'] == 2
    assert state['media']['snapshot'] == original.name
    assert len(telegram.sent) - before == len(state['parts']) + 1
    manual = tmp_path / 'manual-parts'
    manual.mkdir()
    for part in state['parts'] + state['media']['parts']:
        (manual / part['name']).write_bytes(telegram.files[part['file_id']])
    shutil.rmtree(original)
    shutil.rmtree(middle)
    backup.recover(manifest, tmp_path / 'manual-restored', identity, None, manual)
    for name in backup_manifest.FILES:
        assert (tmp_path / 'manual-restored' / name).read_bytes() == (latest / name).read_bytes()


def test_reused_media_download_failure_blocks_success_and_resumes(encrypted_snapshot):
    original, _, recipient = encrypted_snapshot
    telegram = FakeTelegram()
    backup.export(original, recipient, telegram, [111, 222])
    original_state = json.loads((original / '.telegram/delivery.json').read_text())
    assert original_state['version'] == 2
    file_id = original_state['media']['parts'][0]['file_id']
    valid = telegram.files[file_id]
    telegram.files[file_id] = b'corrupt'
    current = next_snapshot(original, '20260922T130000Z')
    with pytest.raises(AssertionError):
        backup.export(current, recipient, telegram, [111, 222])
    assert not (current / 'OFFSITE_OK').exists()
    sent_before = list(telegram.sent)
    telegram.files[file_id] = valid
    backup.export(current, recipient, telegram, [111, 222])
    assert (current / 'OFFSITE_OK').exists()
    assert telegram.sent.count(sent_before[-1]) == 1


def test_changed_media_requires_new_component(encrypted_snapshot):
    original, _, recipient = encrypted_snapshot
    telegram = FakeTelegram()
    backup.export(original, recipient, telegram, [111])
    current = next_snapshot(original, '20260922T130000Z', media=b'changed media')
    backup.export(current, recipient, telegram, [111])
    state = json.loads((current / '.telegram/delivery.json').read_text())
    assert state['version'] == 2
    assert state['media']['snapshot'] == current.name


def test_changed_recipient_does_not_reuse_old_ciphertext(encrypted_snapshot, tmp_path):
    original, _, recipient = encrypted_snapshot
    telegram = FakeTelegram()
    backup.export(original, recipient, telegram, [111])
    identity = tmp_path / 'new-identity.txt'
    subprocess.run(['age-keygen', '-o', str(identity)], check=True, capture_output=True)
    new_recipient = subprocess.check_output(['age-keygen', '-y', str(identity)], text=True).strip()
    current = next_snapshot(original, '20260922T130000Z')
    backup.export(current, new_recipient, telegram, [111])
    manifest = current / '.telegram' / f'{current.name}.manifest.json'
    assert json.loads(manifest.read_text())['media']['snapshot'] == current.name
    backup.recover(manifest, tmp_path / 'new-key-restore', identity, telegram, None)


def test_unverified_snapshot_is_not_a_media_source(encrypted_snapshot):
    original, _, recipient = encrypted_snapshot
    telegram = FakeTelegram()
    backup.export(original, recipient, telegram, [111])
    (original / 'OFFSITE_OK').unlink()
    current = next_snapshot(original, '20260922T130000Z')
    backup.export(current, recipient, telegram, [111])
    state = json.loads((current / '.telegram/delivery.json').read_text())
    assert state['media']['snapshot'] == current.name


def test_reused_media_must_have_been_delivered_to_every_current_admin(encrypted_snapshot):
    original, _, recipient = encrypted_snapshot
    telegram = FakeTelegram()
    backup.export(original, recipient, telegram, [111])
    current = next_snapshot(original, '20260922T130000Z')
    backup.export(current, recipient, telegram, [111, 222])
    state = json.loads((current / '.telegram/delivery.json').read_text())
    assert all(set(p['sent_to']) == {111, 222} for p in state['media']['parts'])


def test_v2_media_metadata_cannot_overwrite_database(encrypted_snapshot, tmp_path):
    snapshot, identity, recipient = encrypted_snapshot
    telegram = FakeTelegram()
    backup.export(snapshot, recipient, telegram, [111])
    manifest_path = snapshot / '.telegram' / f'{snapshot.name}.manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['media']['kind'] = 'database'
    manifest['media']['parts'] = manifest['parts']
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='media component'):
        backup.recover(manifest_path, tmp_path / 'out', identity, telegram, None)


def test_v2_mutated_snapshot_cannot_resume_old_payload(encrypted_snapshot):
    snapshot, _, recipient = encrypted_snapshot
    backup.prepare_v2(snapshot, recipient, [111])
    (snapshot / 'postgres.dump').write_bytes(b'changed after preparation')
    backup_manifest.write_manifest(snapshot)
    with pytest.raises(ValueError, match='Snapshot changed'):
        backup.export(snapshot, recipient, FakeTelegram(), [111])


def test_v2_wrong_media_hash_rejected_after_decryption(encrypted_snapshot, tmp_path):
    snapshot, identity, recipient = encrypted_snapshot
    telegram = FakeTelegram()
    backup.export(snapshot, recipient, telegram, [111])
    manifest_path = snapshot / '.telegram' / f'{snapshot.name}.manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['media']['sha256'] = '0' * 64
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='media checksum'):
        backup.recover(manifest_path, tmp_path / 'out', identity, telegram, None)


def test_component_recovery_rejects_unexpected_archive_members(encrypted_snapshot, tmp_path):
    snapshot, identity, recipient = encrypted_snapshot
    directory = tmp_path / 'parts'
    directory.mkdir()
    component = backup.pack_component(snapshot, recipient, directory, 'media', ('media.tar.gz', 'postgres.dump'))
    output = tmp_path / 'out'
    output.mkdir()
    with pytest.raises(ValueError, match='Unsafe backup archive'):
        backup.recover_component(component, output, identity, None, directory, {'media.tar.gz'})
    assert list(output.iterdir()) == []


def test_component_recovery_rejects_path_traversal(encrypted_snapshot, tmp_path):
    snapshot, identity, _ = encrypted_snapshot
    component = {'kind': 'media', 'snapshot': snapshot.name, 'parts': [
        {'name': '../escape', 'size': 1, 'sha256': '0' * 64},
    ]}
    with pytest.raises(ValueError, match='part name'):
        backup.recover_component(component, tmp_path, identity, None, tmp_path, {'media.tar.gz'})
