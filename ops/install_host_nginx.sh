#!/usr/bin/env bash
set -Eeuo pipefail

app_dir=${1:-/root/arhibot}
target=${2:-/etc/nginx/sites-available/archibot.xn--e1aikcel5c5a.online}
mode=${3:-CHECK}
source_file="${app_dir}/backend/deploy/nginx-archibot.conf"

[[ "${mode}" == "CHECK" || "${mode}" == "APPLY" ]] || {
  echo "Use CHECK for a read-only comparison or APPLY for an approved host Nginx update" >&2
  exit 2
}
[[ -s "${source_file}" ]] || { echo "Missing canonical AuRoom host Nginx config" >&2; exit 1; }
[[ -e "${target}" ]] || { echo "Missing host Nginx site: ${target}" >&2; exit 1; }

nginx -t >/dev/null

if cmp -s "${source_file}" "${target}"; then
  echo "AuRoom host Nginx config is current"
  exit 0
fi

if [[ "${mode}" == "CHECK" ]]; then
  echo "AuRoom host Nginx config differs from the repository candidate"
  exit 3
fi

[[ "${EUID}" -eq 0 ]] || { echo "APPLY requires root" >&2; exit 1; }
backup="${target}.auroom-before-$(date -u +%Y%m%dT%H%M%SZ)"
cp -a "${target}" "${backup}"
restore_previous() {
  echo "Restoring previous Nginx config from ${backup}" >&2
  cp -a "${backup}" "${target}"
  nginx -t
  systemctl reload nginx || true
}

install -m 0644 "${source_file}" "${target}"
if ! nginx -t; then
  echo "Nginx validation failed" >&2
  restore_previous
  exit 1
fi
if ! systemctl reload nginx; then
  echo "Nginx reload failed" >&2
  restore_previous
  exit 1
fi
if ! curl -fsS --connect-timeout 3 --max-time 5 http://127.0.0.1:18080/health/live >/dev/null; then
  echo "Post-reload AuRoom health check failed" >&2
  restore_previous
  exit 1
fi

echo "AuRoom host Nginx config applied; backup=${backup}"
