#!/usr/bin/env bash
set -Eeuo pipefail

app_dir=${1:-/root/arhibot}
compose_file="${app_dir}/backend/docker-compose.yml"
state_dir="${app_dir}/.runtime-monitor"
state_file="${state_dir}/state"
lock_file="${state_dir}/lock"
disk_warn=${AUROOM_MONITOR_DISK_WARN_PCT:-80}
disk_fail=${AUROOM_MONITOR_DISK_FAIL_PCT:-90}
backup_warn_hours=${AUROOM_MONITOR_BACKUP_WARN_HOURS:-30}
backup_fail_hours=${AUROOM_MONITOR_BACKUP_FAIL_HOURS:-36}
generation_stale_minutes=${AUROOM_MONITOR_GENERATION_STALE_MINUTES:-10}

for value in "${disk_warn}" "${disk_fail}" "${backup_warn_hours}" "${backup_fail_hours}" "${generation_stale_minutes}"; do
  [[ "${value}" =~ ^[0-9]+$ ]] || { echo "AuRoom runtime monitor thresholds must be non-negative integers" >&2; exit 2; }
done
(( disk_warn < disk_fail )) || { echo "Disk WARN threshold must be below FAIL threshold" >&2; exit 2; }
(( backup_warn_hours < backup_fail_hours )) || { echo "Backup WARN threshold must be below FAIL threshold" >&2; exit 2; }
command -v flock >/dev/null || { echo "flock is required by AuRoom runtime monitor" >&2; exit 2; }

mkdir -p "${state_dir}"
chmod 700 "${state_dir}"
exec 9>"${lock_file}"
if ! flock -n 9; then
  echo "AuRoom runtime monitor is already running"
  exit 0
fi

if docker compose version >/dev/null 2>&1; then
  compose() { docker compose --project-directory "${app_dir}/backend" -f "${compose_file}" "$@"; }
elif command -v docker-compose >/dev/null 2>&1; then
  compose() { docker-compose --project-directory "${app_dir}/backend" -f "${compose_file}" "$@"; }
else
  echo "Docker Compose is unavailable" >&2
  exit 2
fi

severity=OK
issues=()
metrics=()

warn() {
  [[ "${severity}" == "OK" ]] && severity=WARN
  issues+=("WARN: $*")
}
fail() {
  severity=FAIL
  issues+=("FAIL: $*")
}

disk_used=$(df -P "${app_dir}" | awk 'NR==2 {gsub(/%/, "", $5); print $5}')
metrics+=("disk=${disk_used}%")
if [[ "${disk_used}" =~ ^[0-9]+$ ]]; then
  if (( disk_used >= disk_fail )); then fail "disk usage ${disk_used}% >= ${disk_fail}%";
  elif (( disk_used >= disk_warn )); then warn "disk usage ${disk_used}% >= ${disk_warn}%"; fi
else
  fail "could not determine disk usage"
fi

latest_backup=$(find "${app_dir}/backups/runtime" -mindepth 2 -maxdepth 2 -type f -name SHA256SUMS -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n1 | cut -d' ' -f2- || true)
if [[ -z "${latest_backup}" ]]; then
  fail "no runtime backup checksum found"
else
  backup_epoch=$(stat -c %Y "${latest_backup}")
  now_epoch=$(date +%s)
  backup_age_hours=$(( (now_epoch - backup_epoch) / 3600 ))
  metrics+=("backup_age=${backup_age_hours}h")
  if (( backup_age_hours >= backup_fail_hours )); then fail "runtime backup age ${backup_age_hours}h >= ${backup_fail_hours}h";
  elif (( backup_age_hours >= backup_warn_hours )); then warn "runtime backup age ${backup_age_hours}h >= ${backup_warn_hours}h"; fi
fi

expected_sha=$(awk -F= '$1 == "RELEASE_SHA" {print $2}' "${app_dir}/.release/current.env" 2>/dev/null || true)
if [[ -z "${expected_sha}" ]]; then
  fail "release manifest has no RELEASE_SHA"
else
  metrics+=("release=${expected_sha:0:12}")
fi

if ! curl -fsS --connect-timeout 3 --max-time 8 http://127.0.0.1:18000/health/ready >/dev/null; then
  fail "API readiness failed"
fi
if ! curl -fsS --connect-timeout 3 --max-time 8 http://127.0.0.1:18080/health/live >/dev/null; then
  fail "edge liveness failed"
fi

for service in api bot worker broadcast-worker maintenance frontend nginx postgres redis; do
  container_id=$(compose ps -q "${service}" 2>/dev/null || true)
  if [[ -z "${container_id}" ]]; then
    fail "missing container ${service}"
    continue
  fi
  running=$(docker inspect -f '{{.State.Running}}' "${container_id}" 2>/dev/null || true)
  [[ "${running}" == "true" ]] || fail "container ${service} is not running"
  if [[ "${service}" != "postgres" && "${service}" != "redis" && -n "${expected_sha}" ]]; then
    label=$(docker inspect -f '{{ index .Config.Labels "com.auroom.release" }}' "${container_id}" 2>/dev/null || true)
    [[ "${label}" == "${expected_sha}" ]] || fail "release mismatch ${service}: ${label:-missing}"
  fi
done

for pair in 'worker:generation' 'broadcast-worker:broadcast' 'maintenance:maintenance'; do
  service=${pair%%:*}; worker_name=${pair##*:}
  if ! compose exec -T "${service}" python -m app.workers.heartbeat check "${worker_name}" 45 >/dev/null 2>&1; then
    fail "stale or missing heartbeat for ${service}"
  fi
done

for service in worker broadcast-worker maintenance frontend postgres redis; do
  container_id=$(compose ps -q "${service}" 2>/dev/null || true)
  [[ -n "${container_id}" ]] || continue
  health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "${container_id}" 2>/dev/null || true)
  [[ "${health}" == "healthy" ]] || fail "container health ${service}=${health:-missing}"
done

generation_queued=$(compose exec -T redis redis-cli --raw LLEN auroom:generation_queue 2>/dev/null | tr -d '\r' || echo unknown)
generation_processing=$(compose exec -T redis redis-cli --raw LLEN auroom:generation_processing 2>/dev/null | tr -d '\r' || echo unknown)
broadcast_queued=$(compose exec -T redis redis-cli --raw LLEN auroom:broadcast_queue 2>/dev/null | tr -d '\r' || echo unknown)
metrics+=("generation_queue=${generation_queued}" "generation_processing=${generation_processing}" "broadcast_queue=${broadcast_queued}")

stale_generations=$(compose exec -T postgres psql -U app -d app -Atc "select count(*) from generations where status='processing' and coalesce(started_at, created_at) < now() - interval '${generation_stale_minutes} minutes'" 2>/dev/null | tr -d '[:space:]' || echo unknown)
metrics+=("stale_generations=${stale_generations}")
if [[ "${stale_generations}" =~ ^[0-9]+$ ]]; then
  (( stale_generations == 0 )) || fail "${stale_generations} generation(s) processing longer than ${generation_stale_minutes}m"
else
  fail "could not query stale generations"
fi

summary="AuRoom monitor ${severity}: ${metrics[*]}"
if (( ${#issues[@]} > 0 )); then
  summary+=$'\n'
  summary+=$(printf '%s\n' "${issues[@]}")
fi
echo "${summary}"

fingerprint=$(printf '%s' "${severity}|${issues[*]}" | sha256sum | awk '{print $1}')
previous_severity=""
previous_fingerprint=""
if [[ -s "${state_file}" ]]; then
  IFS='|' read -r previous_severity previous_fingerprint < "${state_file}" || true
fi
should_alert=0
alert_text=""
if [[ -n "${previous_severity}" && "${severity}" == "OK" && "${previous_severity}" != "OK" ]]; then
  should_alert=1
  alert_text="✅ AuRoom runtime восстановлен\n${summary}"
elif [[ "${severity}" != "OK" && ( "${severity}" != "${previous_severity}" || "${fingerprint}" != "${previous_fingerprint}" ) ]]; then
  should_alert=1
  [[ "${severity}" == "FAIL" ]] && icon='🚨' || icon='⚠️'
  alert_text="${icon} AuRoom runtime ${severity}\n${summary}"
fi

state_confirmed=1
if (( should_alert == 1 )); then
  alert_sent=0
  for service in api bot worker; do
    container_id=$(compose ps -q "${service}" 2>/dev/null || true)
    [[ -n "${container_id}" ]] || continue
    if printf '%b' "${alert_text}" | compose exec -T "${service}" python -m app.ops_alert >/dev/null 2>&1; then
      alert_sent=1
      break
    fi
  done
  if (( alert_sent == 0 )); then
    state_confirmed=0
    echo "Warning: could not deliver operations alert to Telegram admins; state will retry next cycle" >&2
  fi
fi

if (( state_confirmed == 1 )); then
  printf '%s|%s\n' "${severity}" "${fingerprint}" > "${state_file}.tmp"
  chmod 600 "${state_file}.tmp"
  mv "${state_file}.tmp" "${state_file}"
fi

[[ "${severity}" != "FAIL" ]]
