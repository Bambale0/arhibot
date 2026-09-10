#!/usr/bin/env bash
set -Eeuo pipefail

app_dir=${1:-/root/arhibot}
mode=${2:-REPORT}
release_root="${app_dir}/.release"
retention_days=${AUROOM_RELEASE_RETENTION_DAYS:-7}
docker_until=${AUROOM_DOCKER_PRUNE_UNTIL:-168h}

[[ "${mode}" == "REPORT" || "${mode}" == "APPLY" ]] || {
  echo "Use REPORT for a read-only report or APPLY for cleanup" >&2
  exit 2
}
[[ "${retention_days}" =~ ^[1-9][0-9]*$ ]] || { echo "Invalid AUROOM_RELEASE_RETENTION_DAYS" >&2; exit 2; }

used_pct=$(df -P "${app_dir}" | awk 'NR==2 {gsub(/%/, "", $5); print $5}')
echo "AuRoom disk used: ${used_pct}%"

candidate_count=$(find "${release_root}" -maxdepth 1 -type d \( -name 'candidate-*' -o -name 'rollback-*' \) -mtime "+${retention_days}" 2>/dev/null | wc -l | tr -d ' ')
dangling_count=$(docker images --filter dangling=true -q 2>/dev/null | sort -u | wc -l | tr -d ' ')
echo "Expired release workdirs: ${candidate_count}"
echo "Dangling Docker images: ${dangling_count}"

if [[ "${mode}" == "REPORT" ]]; then
  echo "Housekeeping is report-only. Run with APPLY only during an approved maintenance action."
  exit 0
fi

find "${release_root}" -maxdepth 1 -type d \( -name 'candidate-*' -o -name 'rollback-*' \) -mtime "+${retention_days}" -print -exec rm -rf {} +
docker image prune -f --filter "until=${docker_until}"
df -h "${app_dir}"
