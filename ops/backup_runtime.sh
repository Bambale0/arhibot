#!/usr/bin/env bash
set -Eeuo pipefail

app_dir=${1:-/root/arhibot}
backup_root=${2:-${app_dir}/backups/runtime}
compose_file="${app_dir}/backend/docker-compose.yml"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
target="${backup_root}/${timestamp}"

if docker compose version >/dev/null 2>&1; then
  compose() { docker compose --project-directory "${app_dir}/backend" -f "${compose_file}" "$@"; }
elif command -v docker-compose >/dev/null 2>&1; then
  compose() { docker-compose --project-directory "${app_dir}/backend" -f "${compose_file}" "$@"; }
else
  echo "Docker Compose is not installed" >&2; exit 1
fi

mkdir -p "${target}"
compose exec -T postgres pg_dump -U app -d app -Fc > "${target}/postgres.dump"
compose exec -T api sh -lc 'cd /data/media && tar -czf - .' > "${target}/media.tar.gz"
sha256sum "${target}/postgres.dump" "${target}/media.tar.gz" > "${target}/SHA256SUMS"

retention_days=$(compose exec -T postgres psql -U app -d app -Atc "select backup_retention_days from operational_settings where id=1" 2>/dev/null | tr -d '[:space:]' || true)
if [[ "${retention_days}" =~ ^[1-9][0-9]*$ ]]; then
  find "${backup_root}" -mindepth 1 -maxdepth 1 -type d -mtime "+${retention_days}" -print -exec rm -rf {} +
fi

echo "AuRoom runtime backup: ${target}"
