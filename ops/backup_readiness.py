#!/usr/bin/env python3
"""Fail a release before runtime mutation unless its snapshot exists off-site."""
import sys
from pathlib import Path
from backup_manifest import verify
from telegram_backup import read_env


def check(app: Path, snapshot: Path) -> None:
    config = read_env(app / '.backup.env')
    if not config.get('AUROOM_BACKUP_AGE_RECIPIENT'):
        raise ValueError('Configure an age public recipient before release')
    if config.get('AUROOM_BACKUP_TRANSPORT') != 'telegram' and not config.get('AUROOM_OFFSITE_BACKUP_REMOTE'):
        raise ValueError('Configure an encrypted off-site transport before release')
    verify(snapshot)
    if not (snapshot / 'OFFSITE_OK').is_file():
        raise ValueError('Release snapshot has no verified off-site export')


if __name__ == '__main__':
    try:
        check(Path(sys.argv[1]), Path(sys.argv[2]))
        print('AuRoom release backup readiness: PASS')
    except (ValueError, OSError) as exc:
        sys.exit(str(exc))
