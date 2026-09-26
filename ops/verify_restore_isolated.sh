#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

app_dir=${1:-/root/arhibot}
backup_dir=${2:?backup directory is required}
compose_file="${app_dir}/backend/docker-compose.yml"
drill_name="auroom-restore-drill-$(date +%s)-$$"
drill_password="restore-drill-local-only-2026"
drill_started=0

if docker compose version >/dev/null 2>&1; then
  compose() { docker compose --project-directory "${app_dir}/backend" -f "${compose_file}" "$@"; }
elif command -v docker-compose >/dev/null 2>&1; then
  compose() { docker-compose --project-directory "${app_dir}/backend" -f "${compose_file}" "$@"; }
else
  echo "Docker Compose is not installed" >&2
  exit 1
fi

cleanup() {
  if (( drill_started == 1 )); then
    docker stop "${drill_name}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

for command_name in docker sha256sum tar; do
  command -v "${command_name}" >/dev/null || {
    echo "${command_name} is required by the isolated restore drill" >&2
    exit 2
  }
done

[[ -s "${backup_dir}/postgres.dump" ]] || { echo "Missing postgres.dump" >&2; exit 1; }
[[ -s "${backup_dir}/media.tar.gz" ]] || { echo "Missing media.tar.gz" >&2; exit 1; }
[[ -s "${backup_dir}/SHA256SUMS" ]] || { echo "Missing SHA256SUMS" >&2; exit 1; }

echo "Verifying backup checksums and media archive"
python3 "${script_dir}/backup_manifest.py" verify "${backup_dir}"
tar -tzf "${backup_dir}/media.tar.gz" >/dev/null
media_entries=$(tar -tzf "${backup_dir}/media.tar.gz" | wc -l | tr -d '[:space:]')

api_id=$(compose ps -q api)
postgres_id=$(compose ps -q postgres)
[[ -n "${api_id}" ]] || { echo "Running AuRoom API container is required to resolve the deployed image" >&2; exit 1; }
[[ -n "${postgres_id}" ]] || { echo "Running AuRoom PostgreSQL container is required to resolve the deployed image" >&2; exit 1; }

api_image=$(docker inspect -f '{{.Image}}' "${api_id}")
postgres_image=$(docker inspect -f '{{.Config.Image}}' "${postgres_id}")
[[ -n "${api_image}" && -n "${postgres_image}" ]] || { echo "Could not resolve deployed images" >&2; exit 1; }

echo "Starting isolated PostgreSQL restore target"
docker run --rm -d \
  --name "${drill_name}" \
  -e POSTGRES_DB=app \
  -e POSTGRES_USER=app \
  -e "POSTGRES_PASSWORD=${drill_password}" \
  "${postgres_image}" >/dev/null
drill_started=1

db_ready=0
for _ in $(seq 1 60); do
  if docker exec "${drill_name}" psql -U app -d app -Atc 'select 1' 2>/dev/null | grep -qx '1'; then
    db_ready=1
    break
  fi
  sleep 1
done
if (( db_ready == 0 )); then
  echo "Isolated PostgreSQL did not become ready" >&2
  docker logs --tail 80 "${drill_name}" >&2 || true
  exit 1
fi

echo "Restoring database into isolated container"
docker exec -i "${drill_name}" \
  pg_restore -U app -d app --no-owner --no-privileges \
  < "${backup_dir}/postgres.dump"

restored_revision=$(docker exec "${drill_name}" \
  psql -U app -d app -Atc 'select version_num from alembic_version' | tr -d '[:space:]')
echo "Restored Alembic revision: ${restored_revision}"

database_url="postgresql+asyncpg://app:${drill_password}@localhost:5432/app"
echo "Migrating isolated restore to the deployed application head"
docker run --rm \
  --network "container:${drill_name}" \
  -e APP_ENV=test \
  -e "DATABASE_URL=${database_url}" \
  "${api_image}" alembic upgrade head

head_revision=$(docker run --rm \
  --network "container:${drill_name}" \
  -e APP_ENV=test \
  -e "DATABASE_URL=${database_url}" \
  "${api_image}" alembic heads | awk 'NR==1 {print $1}')

migrated_revision=$(docker exec "${drill_name}" \
  psql -U app -d app -Atc 'select version_num from alembic_version' | tr -d '[:space:]')
echo "Migrated Alembic revision: ${migrated_revision}"
echo "Application Alembic head: ${head_revision}"

[[ -n "${head_revision}" && "${migrated_revision}" == "${head_revision}" ]] || {
  echo "Isolated restore did not migrate to the deployed application head" >&2
  exit 1
}

echo "Restored row counts:"
for table in users projects generations assets idea_publications questionnaire_applications payments; do
  exists=$(docker exec "${drill_name}" psql -U app -d app -Atc \
    "select to_regclass('public.${table}') is not null" | tr -d '[:space:]')
  if [[ "${exists}" == "t" ]]; then
    count=$(docker exec "${drill_name}" psql -U app -d app -Atc "select count(*) from ${table}" | tr -d '[:space:]')
    printf '  %s=%s\n' "${table}" "${count}"
  fi
done

echo "Media archive entries: ${media_entries}"
echo "AuRoom isolated restore drill: PASS"
