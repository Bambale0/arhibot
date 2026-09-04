#!/usr/bin/env bash
set -Eeuo pipefail

app_dir=${1:-/root/arhibot}
release_sha=${2:?release SHA is required}
compose_file="${app_dir}/backend/docker-compose.yml"
release_root="${app_dir}/.release"
archive="${release_root}/arhibot-source.tar.gz"
checksum="${archive}.sha256"
candidate="${release_root}/candidate-${release_sha}"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_dir="${app_dir}/backups/${timestamp}"
code_backup="${backup_dir}/app-code.tar.gz"
restore_root="${release_root}/rollback-${release_sha}"
mutation_started=0
rollout_succeeded=0

compose() {
  docker compose --project-directory "${app_dir}/backend" -f "${compose_file}" "$@"
}

rollback_code() {
  if [[ ! -s "${code_backup}" ]]; then
    echo "Rollback skipped: previous code backup is unavailable" >&2
    return 0
  fi

  echo "Restoring previous application files"
  rm -rf "${restore_root}"
  mkdir -p "${restore_root}"
  tar -xzf "${code_backup}" -C "${restore_root}"
  rsync --archive --delete \
    --exclude='backend/.env' \
    --exclude='.git/' \
    --exclude='backups/' \
    --exclude='.release/' \
    "${restore_root}/" "${app_dir}/"

  compose build api bot frontend || true
  compose up -d --remove-orphans || true
}

on_exit() {
  status=$?
  if (( status != 0 )) && (( mutation_started == 1 )) && (( rollout_succeeded == 0 )); then
    echo "Rollout failed; restoring previous code" >&2
    rollback_code || true
  fi
  exit "${status}"
}
trap on_exit EXIT

mkdir -p "${app_dir}" "${release_root}" "${backup_dir}"
[[ -f "${app_dir}/backend/.env" ]] || {
  echo "Missing ${app_dir}/backend/.env" >&2
  exit 1
}
[[ -s "${archive}" ]] || { echo "Missing candidate archive" >&2; exit 1; }
[[ -s "${checksum}" ]] || { echo "Missing candidate checksum" >&2; exit 1; }
command -v docker >/dev/null
command -v rsync >/dev/null
command -v curl >/dev/null

cd "${release_root}"
sha256sum --check "$(basename "${checksum}")"

rm -rf "${candidate}"
mkdir -p "${candidate}"
tar -xzf "${archive}" -C "${candidate}"
python3 -m compileall -q "${candidate}/backend/app" "${candidate}/backend/scripts"

if find "${app_dir}" -mindepth 1 -maxdepth 1 \
  ! -name '.release' ! -name 'backups' -print -quit | grep -q .; then
  echo "Creating application backup"
  tar \
    --exclude='./backups' \
    --exclude='./.release' \
    --exclude='./.git' \
    --exclude='./backend/.env' \
    -czf "${code_backup}" -C "${app_dir}" .
  sha256sum "${code_backup}" > "${code_backup}.sha256"
fi

mutation_started=1
rsync --archive --delete \
  --exclude='backend/.env' \
  --exclude='.git/' \
  --exclude='backups/' \
  --exclude='.release/' \
  "${candidate}/" "${app_dir}/"

cd "${app_dir}"
echo "Building API, bot and frontend"
compose build api bot frontend

echo "Applying database migrations"
compose run --rm api alembic upgrade head

echo "Starting production stack"
compose up -d --remove-orphans

health_passed=0
for attempt in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/health/live >/dev/null 2>&1; then
    health_passed=1
    break
  fi
  sleep 3
done

if (( health_passed == 0 )); then
  echo "HTTP health check failed" >&2
  compose ps >&2 || true
  compose logs --tail 100 api nginx frontend 2>&1 \
    | sed -E 's/(token|password|secret|api[_-]?key)=([^[:space:]]+)/\1=[REDACTED]/Ig' >&2 || true
  exit 1
fi

bot_id=$(compose ps -q bot)
if [[ -z "${bot_id}" ]] || [[ "$(docker inspect -f '{{.State.Running}}' "${bot_id}" 2>/dev/null || true)" != "true" ]]; then
  echo "Telegram bot container is not running" >&2
  compose logs --tail 100 bot 2>&1 \
    | sed -E 's/(token|password|secret|api[_-]?key)=([^[:space:]]+)/\1=[REDACTED]/Ig' >&2 || true
  exit 1
fi

rollout_succeeded=1
echo "Deploy SHA: ${release_sha}"
echo "Backup directory: ${backup_dir}"
echo "Arhibot automated rollout passed"
