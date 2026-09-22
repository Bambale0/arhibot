#!/usr/bin/env python3
"""Encrypted, resumable Telegram off-site transport; never sends private age identities."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from backup_manifest import verify

CHUNK_SIZE = 19_000_000  # Below Telegram getFile's 20 MB download limit.
API = 'https://api.telegram.org'


def read_env(path: Path) -> dict[str, str]:
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError('Secret configuration must be a private regular file (0600)')
    values = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip().strip('\"\'')
    return values


def save_json(path: Path, data: dict) -> None:
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2), encoding='utf-8')
    temporary.chmod(0o600)
    temporary.replace(path)


class Telegram:
    def __init__(self, token: str):
        if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', token):
            raise ValueError('Telegram bot token is not configured')
        self.token = token

    def call(self, method: str, fields: dict, document: Path | None = None) -> dict:
        for attempt in range(4):
            boundary = uuid.uuid4().hex
            chunks = []
            for key, value in fields.items():
                chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
            if document:
                chunks.extend([
                    f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{document.name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode(),
                    document.read_bytes(), b'\r\n',
                ])
            chunks.append(f'--{boundary}--\r\n'.encode())
            request = urllib.request.Request(f'{API}/bot{self.token}/{method}', data=b''.join(chunks),
                headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
            delay = min(2 ** attempt, 8)
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    body = json.load(response)
                if body.get('ok'):
                    return body['result']
                code = body.get('error_code', 500)
                delay = min(int(body.get('parameters', {}).get('retry_after', delay)), 60)
                if code != 429 and code < 500:
                    raise ValueError(f'Telegram {method} rejected the request (code {code})')
            except urllib.error.HTTPError as exc:
                if exc.code != 429 and exc.code < 500:
                    raise ValueError(f'Telegram {method} rejected the request (code {exc.code})') from None
                if exc.code == 429:
                    try:
                        delay = min(int(json.load(exc).get('parameters', {}).get('retry_after', delay)), 60)
                    except (ValueError, TypeError):
                        pass
            except (urllib.error.URLError, TimeoutError, OSError):
                pass  # Do not print URLs: they include the credential.
            if attempt < 3:
                time.sleep(delay)
        raise ValueError(f'Telegram {method} failed after bounded retries')

    def download(self, file_id: str, target: Path, expected_hash: str, expected_size: int) -> None:
        remote = self.call('getFile', {'file_id': file_id})
        path = remote.get('file_path', '')
        if not re.fullmatch(r'[A-Za-z0-9_/.-]+', path) or '..' in path.split('/') or path.startswith('/'):
            raise ValueError('Invalid Telegram file path')
        for attempt in range(4):
            try:
                digest = hashlib.sha256()
                count = 0
                with urllib.request.urlopen(f'{API}/file/bot{self.token}/{path}', timeout=120) as response, target.open('wb') as stream:
                    while block := response.read(1024 * 1024):
                        count += len(block)
                        if count > expected_size:
                            raise ValueError('Remote backup part is larger than expected')
                        digest.update(block)
                        stream.write(block)
                if count != expected_size or digest.hexdigest() != expected_hash:
                    raise ValueError('Remote backup checksum mismatch')
                return
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt == 3:
                    raise ValueError('Telegram backup download failed') from None
                time.sleep(2 ** attempt)


def prepare(snapshot: Path, recipient: str) -> tuple[Path, dict]:
    verify(snapshot)
    if not re.fullmatch(r'\d{8}T\d{6}Z', snapshot.name):
        raise ValueError('Snapshot name must be a UTC timestamp')
    state_dir = snapshot / '.telegram'
    state_dir.mkdir(mode=0o700, exist_ok=True)
    state_file = state_dir / 'delivery.json'
    if state_file.exists():
        state = json.loads(state_file.read_text())
        if state['recipient'] != recipient:
            raise ValueError('Recipient changed during an incomplete backup export')
        return state_dir, state
    bundle = state_dir / 'backup.tar.age'
    with tempfile.TemporaryDirectory(prefix='auroom-pack-') as temp:
        archive = Path(temp) / 'backup.tar'
        with tarfile.open(archive, 'w') as tar:
            for name in ('postgres.dump', 'media.tar.gz', 'SHA256SUMS'):
                tar.add(snapshot / name, arcname=name, recursive=False)
        subprocess.run(['age', '--encrypt', '--recipient', recipient, '--output', str(bundle), str(archive)], check=True, capture_output=True)
    parts = []
    with bundle.open('rb') as stream:
        while block := stream.read(CHUNK_SIZE):
            name = f'{snapshot.name}.tar.age.part{len(parts):04d}'
            (state_dir / name).write_bytes(block)
            parts.append({'name': name, 'size': len(block), 'sha256': hashlib.sha256(block).hexdigest()})
    bundle.unlink()
    state = {'version': 1, 'snapshot': snapshot.name, 'recipient': recipient, 'parts': parts, 'deliveries': {}}
    save_json(state_file, state)
    return state_dir, state


def export(snapshot: Path, recipient: str, telegram: Telegram, admin_ids: list[int]) -> None:
    if not admin_ids or any(value <= 0 for value in admin_ids):
        raise ValueError('Backup delivery requires explicit private administrator chat IDs')
    directory, state = prepare(snapshot, recipient)
    for part in state['parts']:
        local = directory / part['name']
        if not part.get('file_id'):
            response = telegram.call('sendDocument', {
                'chat_id': admin_ids[0], 'disable_notification': 'true',
                'caption': f"AuRoom: зашифрованная резервная копия {snapshot.name}. Часть {part['name']}. Ключ хранится отдельно.",
            }, local)
            part['file_id'] = response['document']['file_id']
            part['sent_to'] = [admin_ids[0]]
            save_json(directory / 'delivery.json', state)
        if not part.get('verified'):
            with tempfile.TemporaryDirectory(prefix='auroom-verify-') as temp:
                telegram.download(part['file_id'], Path(temp) / 'part', part['sha256'], part['size'])
            part['verified'] = True
            save_json(directory / 'delivery.json', state)
        for chat_id in admin_ids:
            if chat_id not in part['sent_to']:
                telegram.call('sendDocument', {'chat_id': chat_id, 'document': part['file_id'], 'disable_notification': 'true',
                    'caption': f'AuRoom: зашифрованная копия {snapshot.name}. Ключ хранится отдельно.'})
                part['sent_to'].append(chat_id)
                save_json(directory / 'delivery.json', state)
    manifest = {key: state[key] for key in ('version', 'snapshot', 'recipient')}
    manifest['parts'] = [{key: part[key] for key in ('name', 'size', 'sha256', 'file_id')} for part in state['parts']]
    manifest_path = directory / f'{snapshot.name}.manifest.json'
    save_json(manifest_path, manifest)
    for chat_id in admin_ids:
        if not isinstance(state['deliveries'].get(str(chat_id)), dict):
            response = telegram.call('sendDocument', {'chat_id': chat_id, 'disable_notification': 'true',
                'caption': f'AuRoom: копия {snapshot.name} полностью загружена и проверена. Сохраните manifest и все части; для восстановления нужен отдельный ключ age.'}, manifest_path)
            state['deliveries'][str(chat_id)] = {'message_id': response['message_id'], 'file_id': response['document']['file_id']}
            save_json(directory / 'delivery.json', state)
    manifest_bytes = manifest_path.read_bytes()
    with tempfile.TemporaryDirectory(prefix='auroom-manifest-verify-') as temp:
        telegram.download(state['deliveries'][str(admin_ids[0])]['file_id'], Path(temp) / 'manifest',
            hashlib.sha256(manifest_bytes).hexdigest(), len(manifest_bytes))
    marker = snapshot / 'OFFSITE_OK'
    # Snapshot creation time, not retry time: re-exporting old data must not reset freshness.
    marker.write_text(f'telegram verified {snapshot.name}\n')
    created = (snapshot / 'SHA256SUMS').stat().st_mtime
    os.utime(marker, (created, created))
    print(f'AuRoom encrypted Telegram backup verified: {snapshot.name}; administrators={len(admin_ids)}')


def recover(manifest_path: Path, target: Path, identity: Path, telegram: Telegram | None, parts_dir: Path | None) -> None:
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('version') != 1 or not manifest.get('parts') or len(manifest['parts']) > 10000:
        raise ValueError('Unsupported backup manifest')
    if target.exists() and any(target.iterdir()):
        raise ValueError('Recovery target must be empty')
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='auroom-recover-') as temp:
        root = Path(temp)
        bundle = root / 'backup.tar.age'
        with bundle.open('wb') as output:
            for index, part in enumerate(manifest['parts']):
                name = part['name']
                if not re.fullmatch(r'\d{8}T\d{6}Z.tar.age.part\d{4}', name) or name != f"{manifest['snapshot']}.tar.age.part{index:04d}":
                    raise ValueError('Invalid backup part name/order')
                if not 0 < part['size'] <= CHUNK_SIZE or not re.fullmatch(r'[0-9a-f]{64}', part['sha256']):
                    raise ValueError('Invalid backup part metadata')
                local = root / name
                if parts_dir:
                    source = parts_dir / name
                    if source.is_symlink() or source.stat().st_size != part['size']:
                        raise ValueError('Invalid downloaded backup part')
                    shutil.copyfile(source, local)
                    if hashlib.sha256(local.read_bytes()).hexdigest() != part['sha256']:
                        raise ValueError('Backup part checksum mismatch')
                elif telegram:
                    telegram.download(part['file_id'], local, part['sha256'], part['size'])
                else:
                    raise ValueError('Bot token or manually downloaded parts required')
                with local.open('rb') as stream:
                    shutil.copyfileobj(stream, output)
                local.unlink()
        archive = root / 'backup.tar'
        subprocess.run(['age', '--decrypt', '--identity', str(identity), '--output', str(archive), str(bundle)], check=True, capture_output=True)
        with tarfile.open(archive) as tar:
            entries = tar.getmembers()
            expected = {'postgres.dump', 'media.tar.gz', 'SHA256SUMS'}
            if len(entries) != 3 or {m.name for m in entries} != expected or not all(m.isfile() for m in entries):
                raise ValueError('Unsafe backup archive')
            for entry in entries:
                with tar.extractfile(entry) as source, (target / entry.name).open('wb') as dest:
                    shutil.copyfileobj(source, dest)
                (target / entry.name).chmod(0o600)
        verify(target)
    print('AuRoom encrypted Telegram backup recovered and verified')


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['export', 'recover'])
    parser.add_argument('source', type=Path)
    parser.add_argument('--app-dir', type=Path)
    parser.add_argument('--target', type=Path)
    parser.add_argument('--identity', type=Path)
    parser.add_argument('--parts-dir', type=Path)
    args = parser.parse_args()
    env = read_env(args.app_dir / 'backend/.env') if args.app_dir else os.environ
    if args.command == 'export':
        config = read_env(Path(os.environ.get('AUROOM_BACKUP_ENV_FILE', str(args.app_dir / '.backup.env'))))
        query = "select distinct a.provider_user_id from auth_identities a join users u on u.id=a.user_id where a.provider='telegram' and u.status='active' and u.role in ('admin','superadmin') order by a.provider_user_id"
        result = subprocess.run(['docker', 'compose', '--project-directory', str(args.app_dir / 'backend'),
            '-f', str(args.app_dir / 'backend/docker-compose.yml'), 'exec', '-T', 'postgres',
            'psql', '-U', 'app', '-d', 'app', '-Atc', query], check=True, capture_output=True, text=True)
        admin_ids = [int(value) for value in result.stdout.splitlines() if value.strip()]
        allowed = config.get('AUROOM_BACKUP_TELEGRAM_RECIPIENT_IDS', '').strip()
        if allowed:
            selected = {int(value) for value in allowed.split(',')}
            admin_ids = [value for value in admin_ids if value in selected]
        export(args.source, config['AUROOM_BACKUP_AGE_RECIPIENT'], Telegram(env.get('TELEGRAM_BOT_TOKEN', '')), admin_ids)
    else:
        if not args.target or not args.identity:
            raise ValueError('Recovery requires --target and --identity')
        telegram = None if args.parts_dir else Telegram(env.get('TELEGRAM_BOT_TOKEN', ''))
        recover(args.source, args.target, args.identity, telegram, args.parts_dir)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
        # HTTP/subprocess errors may contain tokens or full secret command arguments.
        print(f'Telegram backup failed ({type(exc).__name__}); check configuration, delivery and archive integrity.', file=sys.stderr)
        sys.exit(1)
