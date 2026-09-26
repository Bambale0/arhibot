import io
import os
from pathlib import Path
import subprocess
import tarfile

REPO = Path(__file__).resolve().parents[2]


def test_failed_snapshot_is_not_scheduled_as_success(tmp_path):
    app = tmp_path / 'app'
    app.mkdir()
    tools = tmp_path / 'bin'
    tools.mkdir()
    archive = tmp_path / 'fixture.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        info = tarfile.TarInfo('image.txt')
        info.size = 5
        tar.addfile(info, io.BytesIO(b'media'))
    docker = tools / 'docker'
    docker.write_text('''#!/usr/bin/env python3
import os,sys
from pathlib import Path
args=' '.join(sys.argv[1:])
if 'version' in args: sys.exit(0)
if 'psql' in args: print(24 if 'interval' in args else 14)
elif 'pg_dump' in args: print('database fixture')
elif 'pg_restore' in args: sys.stdin.buffer.read()
elif 'tar -czf' in args:
    if os.environ.get('FAIL_MEDIA')=='1': sys.exit(1)
    sys.stdout.buffer.write(Path(os.environ['FIXTURE_MEDIA']).read_bytes())
else: sys.exit(1)
''')
    docker.chmod(0o755)
    root = app / 'backups'
    env = {**os.environ, 'PATH': str(tools)+os.pathsep+os.environ['PATH'], 'FIXTURE_MEDIA': str(archive), 'FAIL_MEDIA': '1'}
    command = ['bash', str(REPO / 'ops/backup_runtime.sh'), str(app), str(root), 'scheduled']
    failed = subprocess.run(command, env=env, capture_output=True, text=True)
    assert failed.returncode != 0
    assert not list(root.glob('*/SHA256SUMS'))
    env.pop('FAIL_MEDIA')
    success = subprocess.run(command, env=env, capture_output=True, text=True)
    assert success.returncode == 0, success.stderr
    assert 'AuRoom runtime backup:' in success.stdout
    assert len(list(root.glob('*/SHA256SUMS'))) == 1
    skipped = subprocess.run(command, env=env, capture_output=True, text=True)
    assert skipped.returncode == 0
    assert 'next interval not reached' in skipped.stdout


def test_release_requires_verified_offsite_snapshot(tmp_path):
    import sys
    sys.path.insert(0, str(REPO / 'ops'))
    import backup_manifest
    import backup_readiness
    import pytest
    app = tmp_path / 'app'
    app.mkdir()
    snapshot = app / 'snapshot'
    snapshot.mkdir()
    for name in backup_manifest.FILES:
        (snapshot / name).write_bytes(b'fixture')
    backup_manifest.write_manifest(snapshot)
    config = app / '.backup.env'
    config.write_text('AUROOM_BACKUP_TRANSPORT=telegram\nAUROOM_BACKUP_AGE_RECIPIENT=age-test\n')
    config.chmod(0o600)
    with pytest.raises(ValueError, match='no verified'):
        backup_readiness.check(app, snapshot)
    (snapshot / 'OFFSITE_OK').write_text('verified')
    backup_readiness.check(app, snapshot)
