#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

backup_dir=${1:?backup directory is required}
remote=${AUROOM_OFFSITE_BACKUP_REMOTE:-}
recipient=${AUROOM_BACKUP_AGE_RECIPIENT:-}

if [[ -z "${remote}" && -z "${recipient}" ]]; then
  echo "AuRoom off-site backup export is not configured"
  exit 0
fi
[[ -n "${remote}" && -n "${recipient}" ]] || {
  echo "AUROOM_OFFSITE_BACKUP_REMOTE and AUROOM_BACKUP_AGE_RECIPIENT must be configured together" >&2
  exit 2
}
for command_name in age rclone sha256sum tar; do
  command -v "${command_name}" >/dev/null || {
    echo "${command_name} is required for encrypted off-site backups" >&2
    exit 2
  }
done

[[ -s "${backup_dir}/postgres.dump" ]] || { echo "Missing postgres.dump" >&2; exit 1; }
[[ -s "${backup_dir}/media.tar.gz" ]] || { echo "Missing media.tar.gz" >&2; exit 1; }
[[ -s "${backup_dir}/SHA256SUMS" ]] || { echo "Missing SHA256SUMS" >&2; exit 1; }
(cd "${backup_dir}" && sha256sum -c SHA256SUMS >/dev/null)
tar -tzf "${backup_dir}/media.tar.gz" >/dev/null

snapshot=$(basename "${backup_dir}")
tmp_dir=$(mktemp -d "${backup_dir%/*}/.offsite-${snapshot}.XXXXXX")
trap 'rm -rf "${tmp_dir}"' EXIT
bundle="${tmp_dir}/${snapshot}.tar.age"
checksum="${bundle}.sha256"

# Encrypt before data leaves the host. AUROOM_BACKUP_AGE_RECIPIENT is a public
# age recipient; the private identity is intentionally not needed on the server.
tar -C "${backup_dir}" -cf - postgres.dump media.tar.gz SHA256SUMS   | age --encrypt --recipient "${recipient}" --output "${bundle}"
sha256sum "${bundle}" | awk '{print $1}' > "${checksum}"
chmod 600 "${bundle}" "${checksum}"

remote_dir="${remote%/}/${snapshot}"
rclone copyto "${bundle}" "${remote_dir}/${snapshot}.tar.age" --immutable --checksum
rclone copyto "${checksum}" "${remote_dir}/${snapshot}.tar.age.sha256" --immutable --checksum
local_hash=$(cat "${checksum}")
remote_hash=$(rclone cat "${remote_dir}/${snapshot}.tar.age.sha256" | tr -d '[:space:]')
[[ "${local_hash}" == "${remote_hash}" ]] || {
  echo "Off-site checksum sidecar verification failed" >&2
  exit 1
}

printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "${backup_dir}/OFFSITE_OK"
chmod 600 "${backup_dir}/OFFSITE_OK"
echo "AuRoom encrypted off-site backup exported: ${snapshot}"
