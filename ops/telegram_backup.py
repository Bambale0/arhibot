#!/usr/bin/env python3
"""Encrypted, resumable Telegram off-site transport; never sends private age identities."""
from __future__ import annotations

import argparse
import copy
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

from backup_manifest import digest, verify, write_manifest
import telegram_media as media_archives

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


def pack_component(snapshot: Path, recipient: str, directory: Path, kind: str, names: tuple[str, ...], *, snapshot_name: str | None = None) -> dict:
    """Each component can be restored without any earlier local snapshot."""
    label = snapshot_name or snapshot.name
    parts = []
    with tempfile.TemporaryDirectory(prefix='auroom-component-') as temp:
        archive = Path(temp) / 'component.tar'
        encrypted = Path(temp) / 'component.tar.age'
        with tarfile.open(archive, 'w') as tar:
            for name in names:
                tar.add(snapshot / name, arcname=name, recursive=False)
        subprocess.run(['age', '--encrypt', '--recipient', recipient, '--output', str(encrypted), str(archive)],
            check=True, capture_output=True)
        with encrypted.open('rb') as stream:
            while block := stream.read(CHUNK_SIZE):
                name = f'{label}.{kind}.tar.age.part{len(parts):04d}'
                local = directory / name
                local.write_bytes(block)
                local.chmod(0o600)
                parts.append({'name': name, 'size': len(block), 'sha256': hashlib.sha256(block).hexdigest()})
    return {'kind': kind, 'snapshot': label, 'parts': parts}


def reusable_media(snapshot: Path, recipient: str, admin_ids: list[int], media_hash: str) -> dict | None:
    for previous in sorted(snapshot.parent.iterdir(), reverse=True):
        if previous.name >= snapshot.name or previous.is_symlink() or not re.fullmatch(r'\d{8}T\d{6}Z', previous.name):
            continue
        state_file = previous / '.telegram/delivery.json'
        if not (previous / 'OFFSITE_OK').is_file() or not state_file.is_file() or state_file.is_symlink():
            continue
        try:
            state = json.loads(state_file.read_text())
            if not isinstance(state, dict) or state.get('recipient') != recipient or state.get('version') not in (1, 2):
                continue
            verify(previous)
            if digest(previous / 'media.tar.gz') != media_hash:
                continue
            if state['version'] == 1:
                media = {'kind': 'legacy-v1-bundle', 'snapshot': state['snapshot'], 'parts': state['parts'], 'sha256': media_hash}
            else:
                media = state['media']
                if media['sha256'] != media_hash:
                    continue
            validate_component(media)
            if not all(p.get('file_id') and p.get('verified') and set(admin_ids).issubset(p.get('sent_to', [])) for p in media['parts']):
                continue
            result = copy.deepcopy(media)
            # Every new snapshot proves that reused remote bytes still exist.
            for part in result['parts']:
                part['verified'] = False
            return result
        except (ValueError, KeyError, TypeError, OSError):
            continue  # An incomplete/invalid cache entry is never a reuse source.
    return None


def prepare_v2(snapshot: Path, recipient: str, admin_ids: list[int]) -> tuple[Path, dict]:
    verify(snapshot)
    if not re.fullmatch(r'\d{8}T\d{6}Z', snapshot.name):
        raise ValueError('Snapshot name must be a UTC timestamp')
    directory = snapshot / '.telegram'
    directory.mkdir(mode=0o700, exist_ok=True)
    state_file = directory / 'delivery.json'
    if state_file.exists():
        # Preserve partially delivered v1 snapshots; never reinterpret their parts.
        directory, state = prepare(snapshot, recipient)
        if state.get('version') not in (1, 2):
            raise ValueError('Unsupported backup delivery state')
        if state['version'] == 2 and state.get('checksums_sha256') != digest(snapshot / 'SHA256SUMS'):
            raise ValueError('Snapshot changed during an incomplete backup export')
        return directory, state
    media_hash = digest(snapshot / 'media.tar.gz')
    media = reusable_media(snapshot, recipient, admin_ids, media_hash)
    if media is None:
        media = pack_component(snapshot, recipient, directory, 'media', ('media.tar.gz',))
        media['sha256'] = media_hash
    database = pack_component(snapshot, recipient, directory, 'database', ('postgres.dump', 'SHA256SUMS'))
    state = {'version': 2, 'snapshot': snapshot.name, 'recipient': recipient,
        'checksums_sha256': digest(snapshot / 'SHA256SUMS'), 'parts': database['parts'],
        'media': media, 'deliveries': {}}
    save_json(state_file, state)
    return directory, state


def media_components(state: dict) -> list[dict]:
    if state['version'] == 1:
        return []
    if state['version'] == 2:
        return [state['media']]
    media = state['media']
    if not isinstance(media, dict):
        raise ValueError('Invalid incremental media descriptor')
    base, deltas = media.get('base'), media.get('deltas')
    validate_component(base)
    if base['kind'] not in ('media', 'legacy-v1-bundle') or not isinstance(deltas, list) or len(deltas) > media_archives.MAX_DELTAS:
        raise ValueError('Invalid incremental media components')
    if base['snapshot'] > state['snapshot'] or not isinstance(base.get('sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', base['sha256']):
        raise ValueError('Invalid incremental baseline')
    last = base['snapshot']
    for delta in deltas:
        validate_component(delta)
        if delta['kind'] != 'media-delta' or not last < delta['snapshot'] <= state['snapshot']:
            raise ValueError('Invalid incremental media order')
        last = delta['snapshot']
    return [base, *deltas]


def incremental_source(snapshot: Path, recipient: str, admin_ids: list[int]) -> tuple[dict, dict] | None:
    for previous in sorted(snapshot.parent.iterdir(), reverse=True):
        if previous.name >= snapshot.name or previous.is_symlink() or not re.fullmatch(r'\d{8}T\d{6}Z', previous.name):
            continue
        state_file = previous / '.telegram/delivery.json'
        if not (previous / 'OFFSITE_OK').is_file() or not state_file.is_file() or state_file.is_symlink():
            continue
        try:
            state = json.loads(state_file.read_text())
            if not isinstance(state, dict) or state.get('version') not in (1, 2, 3) or state.get('recipient') != recipient:
                continue
            verify(previous)
            if state['version'] == 1:
                base = {'kind': 'legacy-v1-bundle', 'snapshot': state['snapshot'],
                        'parts': state['parts'], 'sha256': digest(previous / 'media.tar.gz')}
                components = [base]
            else:
                components = media_components(state)
            if not all(p.get('file_id') and p.get('verified') and set(admin_ids).issubset(p.get('sent_to', []))
                       for component in components for p in component['parts']):
                continue
            old_index = media_archives.inventory(previous / 'media.tar.gz')
            if state['version'] == 3:
                baseline = state['baseline_index']
                media_archives.validate_index(baseline)
                media = copy.deepcopy(state['media'])
            else:
                baseline = old_index
                media = {'base': copy.deepcopy(components[0]), 'deltas': []}
            # The complete descriptor and baseline index travel with every new
            # snapshot; local retention never creates a recursive dependency.
            return {'media': media, 'baseline_index': baseline}, old_index
        except (ValueError, KeyError, TypeError, OSError, tarfile.TarError):
            continue
    return None


def prepare_incremental(snapshot: Path, recipient: str, admin_ids: list[int]) -> tuple[Path, dict]:
    verify(snapshot)
    if not re.fullmatch(r'\d{8}T\d{6}Z', snapshot.name):
        raise ValueError('Snapshot name must be a UTC timestamp')
    directory = snapshot / '.telegram'
    state_file = directory / 'delivery.json'
    if state_file.exists():
        directory, state = prepare(snapshot, recipient)
        if state.get('version') not in (1, 2, 3):
            raise ValueError('Unsupported backup delivery state')
        if state['version'] != 1 and state.get('checksums_sha256') != digest(snapshot / 'SHA256SUMS'):
            raise ValueError('Snapshot changed during an incomplete backup export')
        if state['version'] == 3:
            media_components(state)
        return directory, state
    source = incremental_source(snapshot, recipient, admin_ids)
    if source is None:
        return prepare_v2(snapshot, recipient, admin_ids)
    directory.mkdir(mode=0o700, exist_ok=True)
    original_checksums = digest(snapshot / 'SHA256SUMS')
    try:
        current_index = media_archives.inventory(snapshot / 'media.tar.gz')
    except tarfile.ReadError:
        # Historical v1/v2 transport accepts opaque archives; preserve that
        # compatibility rather than reinterpret their payload as a delta.
        return prepare_v2(snapshot, recipient, admin_ids)
    state, previous_index = source
    media = state['media']
    changed = media_archives.changed_files(current_index, previous_index)
    if changed and len(media['deltas']) >= media_archives.MAX_DELTAS:
        # Compact only the overlay. The large verified baseline is never resent
        # merely because many tiny daily changes reached the chain bound.
        changed = media_archives.changed_files(current_index, state['baseline_index'])
        media['deltas'] = []
    if changed:
        delta = directory / 'media-delta.tar.gz'
        media_archives.make_delta(snapshot / 'media.tar.gz', delta, current_index, changed)
        media['deltas'].append(pack_component(directory, recipient, directory, 'media-delta', ('media-delta.tar.gz',), snapshot_name=snapshot.name))
        delta.unlink()
    index = {'version': 1, 'files': current_index, 'baseline_files': state['baseline_index'],
             'database_sha256': digest(snapshot / 'postgres.dump'),
             'source_media_sha256': digest(snapshot / 'media.tar.gz')}
    save_json(directory / 'media-index.json', index)
    if (directory / 'media-index.json').stat().st_size > 64 * 1024 * 1024:
        raise ValueError('Incremental media index exceeds recovery limit')
    with tempfile.TemporaryDirectory(prefix='auroom-database-index-') as temporary:
        payload = Path(temporary) / snapshot.name
        payload.mkdir()
        for name in ('postgres.dump', 'SHA256SUMS'):
            shutil.copyfile(snapshot / name, payload / name)
        shutil.copyfile(directory / 'media-index.json', payload / 'media-index.json')
        database = pack_component(payload, recipient, directory, 'database-v3',
                                  ('postgres.dump', 'SHA256SUMS', 'media-index.json'))
    verify(snapshot)
    if digest(snapshot / 'SHA256SUMS') != original_checksums or media_archives.inventory(snapshot / 'media.tar.gz') != current_index:
        raise ValueError('Snapshot changed during incremental preparation')
    for component in [media['base'], *media['deltas']]:
        for part in component['parts']:
            if part.get('file_id'):
                part['verified'] = False
    state.update(version=3, snapshot=snapshot.name, recipient=recipient,
                 checksums_sha256=original_checksums, parts=database['parts'], deliveries={},
                 index_sha256=digest(directory / 'media-index.json'))
    save_json(state_file, state)
    return directory, state


def public_parts(parts: list[dict]) -> list[dict]:
    return [{key: part[key] for key in ('name', 'size', 'sha256', 'file_id')} for part in parts]


def export(snapshot: Path, recipient: str, telegram: Telegram, admin_ids: list[int]) -> None:
    if not admin_ids or any(value <= 0 for value in admin_ids):
        raise ValueError('Backup delivery requires explicit private administrator chat IDs')
    directory, state = prepare_incremental(snapshot, recipient, admin_ids)
    parts = state['parts'] + [part for component in media_components(state) for part in component['parts']]
    for part in parts:
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
    manifest['parts'] = public_parts(state['parts'])
    if state['version'] == 2:
        manifest['media'] = {key: state['media'][key] for key in ('kind', 'snapshot', 'sha256')}
        manifest['media']['parts'] = public_parts(state['media']['parts'])
    if state['version'] == 3:
        manifest['media'] = {
            'base': {**{key: state['media']['base'][key] for key in ('kind', 'snapshot', 'sha256')},
                     'parts': public_parts(state['media']['base']['parts'])},
            'deltas': [{**{key: component[key] for key in ('kind', 'snapshot')},
                        'parts': public_parts(component['parts'])} for component in state['media']['deltas']],
        }
        manifest['index_sha256'] = state['index_sha256']
    manifest_path = directory / f'{snapshot.name}.manifest.json'
    save_json(manifest_path, manifest)
    manifest_caption = f'AuRoom: копия {snapshot.name} полностью загружена и проверена. Сохраните manifest и все части; для восстановления нужен отдельный ключ age.'
    if state['version'] in (2, 3):
        manifest_caption += ' Части медиа могут быть из предыдущих копий: они перечислены в manifest и нужны для восстановления.'
    for chat_id in admin_ids:
        if not isinstance(state['deliveries'].get(str(chat_id)), dict):
            response = telegram.call('sendDocument', {'chat_id': chat_id, 'disable_notification': 'true',
                'caption': manifest_caption}, manifest_path)
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


def validate_component(component: dict) -> None:
    if not isinstance(component, dict):
        raise ValueError('Unsupported backup component')
    kind = component.get('kind')
    snapshot = component.get('snapshot', '')
    parts = component.get('parts')
    if kind not in ('legacy-v1-bundle', 'database', 'media', 'database-v3', 'media-delta') or not isinstance(snapshot, str) or not re.fullmatch(r'\d{8}T\d{6}Z', snapshot):
        raise ValueError('Unsupported backup component')
    if not isinstance(parts, list) or not parts or len(parts) > 10000:
        raise ValueError('Unsupported backup manifest')
    prefix = snapshot if kind == 'legacy-v1-bundle' else f'{snapshot}.{kind}'
    for index, part in enumerate(parts):
        if not isinstance(part, dict) or part.get('name') != f'{prefix}.tar.age.part{index:04d}':
            raise ValueError('Invalid backup part name/order')
        size, checksum = part.get('size'), part.get('sha256')
        if type(size) is not int or not 0 < size <= CHUNK_SIZE or not isinstance(checksum, str) or not re.fullmatch(r'[0-9a-f]{64}', checksum):
            raise ValueError('Invalid backup part metadata')


def recover_component(component: dict, target: Path, identity: Path, telegram: Telegram | None,
                      parts_dir: Path | None, selected: set[str]) -> None:
    validate_component(component)
    with tempfile.TemporaryDirectory(prefix='auroom-recover-') as temp:
        root = Path(temp)
        bundle = root / 'backup.tar.age'
        with bundle.open('wb') as output:
            for part in component['parts']:
                name = part['name']
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
            expected = {
                'legacy-v1-bundle': {'postgres.dump', 'media.tar.gz', 'SHA256SUMS'},
                'database': {'postgres.dump', 'SHA256SUMS'},
                'media': {'media.tar.gz'},
                'media-delta': {'media-delta.tar.gz'},
                'database-v3': {'postgres.dump', 'SHA256SUMS', 'media-index.json'},
            }[component['kind']]
            if len(entries) != len(expected) or {m.name for m in entries} != expected or not all(m.isfile() for m in entries):
                raise ValueError('Unsafe backup archive')
            for entry in entries:
                if entry.name not in selected:
                    continue
                with tar.extractfile(entry) as source, (target / entry.name).open('wb') as dest:
                    shutil.copyfileobj(source, dest)
                (target / entry.name).chmod(0o600)


def recover_incremental_media(manifest: dict, target: Path, identity: Path,
                              telegram: Telegram | None, parts_dir: Path | None) -> None:
    components = media_components(manifest)
    index_path = target / 'media-index.json'
    if index_path.stat().st_size > 64 * 1024 * 1024 or digest(index_path) != manifest.get('index_sha256'):
        raise ValueError('Incremental media index checksum mismatch')
    index = json.loads(index_path.read_text())
    if not isinstance(index, dict) or index.get('version') != 1:
        raise ValueError('Unsupported incremental media index')
    media_archives.validate_index(index['files'])
    media_archives.validate_index(index['baseline_files'])
    if digest(target / 'postgres.dump') != index.get('database_sha256'):
        raise ValueError('Incremental database checksum mismatch')
    checksums = {}
    original = target / 'SHA256SUMS'
    if original.stat().st_size > 16384:
        raise ValueError('Invalid source checksums')
    for line in original.read_text().splitlines():
        match = re.fullmatch(r'([0-9a-f]{64}) [ *](.+)', line)
        if not match:
            raise ValueError('Invalid source checksums')
        raw = match[2]
        name = Path(raw).name
        if '..' in Path(raw).parts or (not Path(raw).is_absolute() and raw != name) or name not in ('postgres.dump', 'media.tar.gz') or name in checksums:
            raise ValueError('Invalid source checksum path')
        checksums[name] = match[1]
    if checksums != {'postgres.dump': index['database_sha256'], 'media.tar.gz': index['source_media_sha256']}:
        raise ValueError('Source checksums do not match incremental index')
    with tempfile.TemporaryDirectory(prefix='auroom-media-rebuild-') as temporary:
        root = Path(temporary)
        cache = root / 'content'
        cache.mkdir()
        for number, component in enumerate(components):
            stage = root / str(number)
            stage.mkdir()
            name = 'media.tar.gz' if number == 0 else 'media-delta.tar.gz'
            recover_component(component, stage, identity, telegram, parts_dir, {name})
            if number == 0 and digest(stage / name) != component.get('sha256'):
                raise ValueError('Baseline media checksum mismatch')
            actual = media_archives.inventory(stage / name, wanted=index['files'], cache=cache)
            if number == 0 and actual != index['baseline_files']:
                raise ValueError('Baseline media index mismatch')
            shutil.rmtree(stage)
        media_archives.assemble(target / 'media.tar.gz', index['files'], cache)
    # Logical file contents/metadata are verified above. Gzip bytes are newly
    # encoded, so retain original transport checksums explicitly as provenance.
    original.rename(target / 'SOURCE_SHA256SUMS')
    write_manifest(target)


def recover(manifest_path: Path, target: Path, identity: Path, telegram: Telegram | None, parts_dir: Path | None) -> None:
    manifest = json.loads(manifest_path.read_text())
    if not isinstance(manifest, dict) or manifest.get('version') not in (1, 2, 3):
        raise ValueError('Unsupported backup manifest')
    if target.exists() and any(target.iterdir()):
        raise ValueError('Recovery target must be empty')
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    component = {'kind': {1: 'legacy-v1-bundle', 2: 'database', 3: 'database-v3'}[manifest['version']],
        'snapshot': manifest.get('snapshot'), 'parts': manifest.get('parts')}
    recover_component(component, target, identity, telegram, parts_dir, {'postgres.dump', 'SHA256SUMS', 'media.tar.gz', 'media-index.json'})
    if manifest['version'] == 2:
        media = manifest.get('media', {})
        if not isinstance(media, dict) or media.get('kind') not in ('media', 'legacy-v1-bundle'):
            raise ValueError('Unsupported backup media component')
        recover_component(media, target, identity, telegram, parts_dir, {'media.tar.gz'})
        if digest(target / 'media.tar.gz') != media.get('sha256'):
            raise ValueError('Recovered media checksum mismatch')
    if manifest['version'] == 3:
        recover_incremental_media(manifest, target, identity, telegram, parts_dir)
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
    except (ValueError, OSError, KeyError, tarfile.TarError, subprocess.SubprocessError) as exc:
        # HTTP/subprocess errors may contain tokens or full secret command arguments.
        print(f'Telegram backup failed ({type(exc).__name__}); check configuration, delivery and archive integrity.', file=sys.stderr)
        sys.exit(1)
