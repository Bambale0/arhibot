#!/usr/bin/env bash
set -Eeuo pipefail

app_dir=${1:-/root/arhibot}
backup_dir=${2:?backup directory is required}
confirm=${3:-}
compose_file="${app_dir}/backend/docker-compose.yml"

[[ "${confirm}" == "RESTORE" ]] || { echo "Refusing restore without explicit RESTORE confirmation" >&2; exit 2; }
[[ -s "${backup_dir}/postgres.dump" ]] || { echo "Missing postgres.dump" >&2; exit 1; }
[[ -s "${backup_dir}/media.tar.gz" ]] || { echo "Missing media.tar.gz" >&2; exit 1; }
[[ -s "${backup_dir}/SHA256SUMS" ]] || { echo "Missing SHA256SUMS" >&2; exit 1; }
(cd "${backup_dir}" && sha256sum -c SHA256SUMS)

if docker compose version >/dev/null 2>&1; then
  compose() { docker compose --project-directory "${app_dir}/backend" -f "${compose_file}" "$@"; }
elif command -v docker-compose >/dev/null 2>&1; then
  compose() { docker-compose --project-directory "${app_dir}/backend" -f "${compose_file}" "$@"; }
else
  echo "Docker Compose is not installed" >&2; exit 1
fi

compose stop api bot worker broadcast-worker maintenance nginx frontend
compose exec -T postgres psql -U app -d postgres -v ON_ERROR_STOP=1 <<'SQL'
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'app' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS app;
CREATE DATABASE app OWNER app;
SQL
compose exec -T postgres pg_restore -U app -d app --no-owner --no-privileges < "${backup_dir}/postgres.dump"
compose run --rm -T api sh -lc 'rm -rf /data/media/* && tar -xzf - -C /data/media' < "${backup_dir}/media.tar.gz"
compose up -d --remove-orphans
compose up -d --force-recreate nginx

for attempt in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:18000/health/ready >/dev/null 2>&1 && curl -fsS http://127.0.0.1:18080/health/live >/dev/null 2>&1; then
    echo "AuRoom runtime restore passed"
    exit 0
  fi
  sleep 3
done

echo "Restore completed but health checks failed" >&2
compose ps >&2 || true
exit 1
