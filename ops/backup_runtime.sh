#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

app_dir=${1:-/root/arhibot}
backup_root=${2:-${app_dir}/backups/runtime}
mode=${3:-scheduled}
compose_file="${app_dir}/backend/docker-compose.yml"
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
backup_env=${AUROOM_BACKUP_ENV_FILE:-${app_dir}/.backup.env}

mkdir -p "${app_dir}" "${backup_root}"
command -v flock >/dev/null || { echo "flock is required by AuRoom backup" >&2; exit 1; }
if [[ "${AUROOM_RUNTIME_LOCK_HELD:-0}" != "1" ]]; then
  exec 9>"${app_dir}/.runtime-mutation.lock"
  if ! flock -n 9; then
    if [[ "${mode}" == "scheduled" ]]; then
      echo "AuRoom backup skipped: another runtime mutation is in progress"
      exit 0
    fi
    echo "AuRoom backup refused: another runtime mutation is in progress" >&2
    exit 75
  fi
  export AUROOM_RUNTIME_LOCK_HELD=1
fi

if docker compose version >/dev/null 2>&1; then
  compose() { docker compose --project-directory "${app_dir}/backend" -f "${compose_file}" "$@"; }
elif command -v docker-compose >/dev/null 2>&1; then
  compose() { docker-compose --project-directory "${app_dir}/backend" -f "${compose_file}" "$@"; }
else
  echo "Docker Compose is not installed" >&2; exit 1
fi

interval_hours=$(compose exec -T postgres psql -U app -d app -Atc "select backup_interval_hours from operational_settings where id=1" 2>/dev/null | tr -d '[:space:]' || true)
if [[ "${mode}" != "force" ]]; then
  if [[ ! "${interval_hours}" =~ ^[1-9][0-9]*$ ]]; then
    echo "AuRoom backup skipped: automatic backup interval is disabled"
    exit 0
  fi
  latest_epoch=$(find "${backup_root}" -mindepth 1 -maxdepth 1 -type d -printf '%T@\n' 2>/dev/null | sort -nr | head -n1 | cut -d. -f1 || true)
  now_epoch=$(date +%s)
  if [[ "${latest_epoch}" =~ ^[0-9]+$ ]] && (( now_epoch - latest_epoch < interval_hours * 3600 )); then
    echo "AuRoom backup skipped: next interval not reached"
    exit 0
  fi
fi

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
target="${backup_root}/${timestamp}"
install -d -m 700 "${target}"
compose exec -T postgres pg_dump -U app -d app -Fc > "${target}/postgres.dump"
compose exec -T api sh -lc 'cd /data/media && tar -czf - .' > "${target}/media.tar.gz"
chmod 600 "${target}/postgres.dump" "${target}/media.tar.gz"
sha256sum "${target}/postgres.dump" "${target}/media.tar.gz" > "${target}/SHA256SUMS"
chmod 600 "${target}/SHA256SUMS"

# Verify both backup streams before advertising the snapshot as usable.
tar -tzf "${target}/media.tar.gz" >/dev/null
compose exec -T postgres pg_restore --list < "${target}/postgres.dump" >/dev/null

if [[ -f "${backup_env}" ]]; then
  backup_env_mode=$(stat -c '%a' "${backup_env}")
  if (( 10#${backup_env_mode} % 100 != 0 )); then
    echo "Backup config must not be readable/writable by group or others: ${backup_env}" >&2
    exit 1
  fi
  read_backup_value() {
    python3 - "${backup_env}" "$1" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
key = sys.argv[2]
for raw in path.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    current, value = line.split("=", 1)
    if current.strip() != key:
        continue
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    print(value, end="")
    break
PY
  }
  offsite_remote=$(read_backup_value AUROOM_OFFSITE_BACKUP_REMOTE)
  age_recipient=$(read_backup_value AUROOM_BACKUP_AGE_RECIPIENT)
  if [[ -n "${offsite_remote}" || -n "${age_recipient}" ]]; then
    AUROOM_OFFSITE_BACKUP_REMOTE="${offsite_remote}"     AUROOM_BACKUP_AGE_RECIPIENT="${age_recipient}"       "${script_dir}/export_offsite_backup.sh" "${target}"
  fi
fi

retention_days=$(compose exec -T postgres psql -U app -d app -Atc "select backup_retention_days from operational_settings where id=1" 2>/dev/null | tr -d '[:space:]' || true)
if [[ "${retention_days}" =~ ^[1-9][0-9]*$ ]]; then
  find "${backup_root}" -mindepth 1 -maxdepth 1 -type d -mtime "+${retention_days}" -print -exec rm -rf {} +
fi

echo "AuRoom runtime backup: ${target}"
