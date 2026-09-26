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


def test_encrypted_admin_delivery_download_and_restore(encrypted_snapshot, tmp_path):
    snapshot, identity, recipient = encrypted_snapshot
    telegram = FakeTelegram()
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


def test_partial_delivery_never_marks_success_and_resumes(encrypted_snapshot):
    snapshot, _, recipient = encrypted_snapshot
    telegram = FakeTelegram()
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
