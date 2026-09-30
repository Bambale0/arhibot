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


def test_disabled_backup_never_dumps_even_when_forced(tmp_path):
    app = tmp_path / 'app'
    tools = tmp_path / 'bin'
    tools.mkdir()
    docker = tools / 'docker'
    docker.write_text("""#!/usr/bin/env python3
import sys
args=' '.join(sys.argv[1:])
if 'version' in args: sys.exit(0)
if 'psql' in args: print(0); sys.exit(0)
raise SystemExit('Unexpected dump/export: '+args)
""")
    docker.chmod(0o755)
    env = {**os.environ, 'PATH': str(tools)+os.pathsep+os.environ['PATH']}
    for mode in ('scheduled', 'force'):
        result = subprocess.run(['bash', str(REPO / 'ops/backup_runtime.sh'), str(app),
                                 str(app/'backups'), mode], env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert 'runtime backups disabled by operator' in result.stdout
        assert not list((app/'backups').glob('*/postgres.dump'))


def test_unreadable_backup_policy_fails_closed(tmp_path):
    tools = tmp_path / 'bin'
    tools.mkdir()
    docker = tools / 'docker'
    docker.write_text("#!/bin/sh\ncase \"$*\" in *version*) exit 0;; *) exit 1;; esac\n")
    docker.chmod(0o755)
    env = {**os.environ, 'PATH': str(tools)+os.pathsep+os.environ['PATH']}
    for mode in ('scheduled', 'force'):
        result = subprocess.run(['bash', str(REPO / 'ops/backup_runtime.sh'), str(tmp_path/'app'),
                                 str(tmp_path/'backups'), mode], env=env, capture_output=True, text=True)
        assert result.returncode != 0
        assert 'Cannot read valid backup policy' in result.stderr


def test_monitor_respects_disabled_backups_but_keeps_other_health_checks(tmp_path):
    app = tmp_path / 'app'
    (app / '.release').mkdir(parents=True)
    (app / '.release/current.env').write_text('RELEASE_SHA=fixture\n')
    (app / '.backup.env').write_text('AUROOM_BACKUP_TRANSPORT=telegram\nAUROOM_BACKUP_AGE_RECIPIENT=fixture\n')
    tools = tmp_path / 'bin'
    tools.mkdir()
    docker = tools / 'docker'
    docker.write_text('''#!/usr/bin/env python3
import os,sys
args=' '.join(sys.argv[1:])
if 'version' in args: sys.exit(0)
if 'inspect' in args:
    print('true' if 'Running' in args else 'healthy' if 'Health' in args else 'fixture')
elif 'ps -q' in args: print('fixture')
elif 'backup_interval_hours' in args: print(os.environ['BACKUP_INTERVAL'])
elif 'psql' in args or 'LLEN' in args: print(0)
elif 'heartbeat' in args: pass
elif 'ops_alert' in args:
    sys.stdin.read()
    with open(os.environ['ALERT_FILE'],'a') as out: out.write('alert\\n')
else: raise SystemExit('Unhandled '+args)
''')
    docker.chmod(0o755)
    curl = tools / 'curl'
    curl.write_text('#!/bin/sh\nexit "${FAIL_READINESS:-0}"\n')
    curl.chmod(0o755)
    disk_usage = tools / 'df'
    disk_usage.write_text(
        '#!/bin/sh\nprintf "Filesystem Blocks Used Available Capacity Mounted\\n'
        'fixture 100 50 50 50%% /\\n"\n'
    )
    disk_usage.chmod(0o755)
    alerts = tmp_path / 'alerts'
    env = {**os.environ, 'PATH': str(tools)+os.pathsep+os.environ['PATH'],
           'ALERT_FILE':str(alerts), 'BACKUP_INTERVAL':'0',
           'AUROOM_MONITOR_DISK_WARN_PCT':'99', 'AUROOM_MONITOR_DISK_FAIL_PCT':'100'}
    command = ['bash', str(REPO / 'ops/runtime_monitor.sh'), str(app)]
    disabled = subprocess.run(command, env=env, capture_output=True, text=True)
    assert disabled.returncode == 0, disabled.stdout + disabled.stderr
    assert 'backup=disabled_by_operator' in disabled.stdout
    assert not alerts.exists()
    enabled = subprocess.run(command, env={**env,'BACKUP_INTERVAL':'24'}, capture_output=True, text=True)
    assert enabled.returncode != 0
    assert 'no runtime backup checksum' in enabled.stdout
    unreadable = subprocess.run(command, env={**env,'BACKUP_INTERVAL':''}, capture_output=True, text=True)
    assert unreadable.returncode != 0
    assert 'could not read backup policy' in unreadable.stdout
    unhealthy = subprocess.run(command, env={**env,'FAIL_READINESS':'1'}, capture_output=True, text=True)
    assert unhealthy.returncode != 0
    assert 'API readiness failed' in unhealthy.stdout
