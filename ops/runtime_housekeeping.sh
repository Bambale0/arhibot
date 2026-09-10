#!/usr/bin/env bash
set -Eeuo pipefail

app_dir=${1:-/root/arhibot}
mode=${2:-REPORT}
release_root="${app_dir}/.release"
retention_days=${AUROOM_RELEASE_RETENTION_DAYS:-7}

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
docker system df || true

if [[ "${mode}" == "REPORT" ]]; then
  echo "Housekeeping is report-only. APPLY removes expired release workdirs, dangling images, and unused build cache."
  exit 0
fi

find "${release_root}" -maxdepth 1 -type d \( -name 'candidate-*' -o -name 'rollback-*' \) -mtime "+${retention_days}" -print -exec rm -rf {} +
# Dangling images and builder cache are not referenced by running containers.
# Rollback is source-backup/rebuild based, so retaining these artifacts only consumes disk.
docker image prune -f
docker builder prune -f
df -h "${app_dir}"
