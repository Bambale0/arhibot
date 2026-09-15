#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

remote_snapshot=${1:?remote snapshot directory is required}
target_dir=${2:?local target directory is required}
identity_file=${AUROOM_BACKUP_AGE_IDENTITY_FILE:-}

[[ -n "${identity_file}" && -f "${identity_file}" ]] || {
  echo "AUROOM_BACKUP_AGE_IDENTITY_FILE must point to the age private identity" >&2
  exit 2
}
for command_name in age rclone sha256sum tar; do
  command -v "${command_name}" >/dev/null || {
    echo "${command_name} is required for off-site backup recovery" >&2
    exit 2
  }
done

snapshot=$(basename "${remote_snapshot%/}")
install -d -m 700 "${target_dir}"
tmp_dir=$(mktemp -d "${target_dir%/*}/.offsite-restore-${snapshot}.XXXXXX")
trap 'rm -rf "${tmp_dir}"' EXIT
bundle="${tmp_dir}/${snapshot}.tar.age"
checksum="${tmp_dir}/${snapshot}.tar.age.sha256"

rclone copyto "${remote_snapshot%/}/${snapshot}.tar.age" "${bundle}"
rclone copyto "${remote_snapshot%/}/${snapshot}.tar.age.sha256" "${checksum}"
expected=$(tr -d '[:space:]' < "${checksum}")
actual=$(sha256sum "${bundle}" | awk '{print $1}')
[[ "${expected}" == "${actual}" ]] || {
  echo "Encrypted off-site backup checksum mismatch" >&2
  exit 1
}

age --decrypt --identity "${identity_file}" "${bundle}"   | tar -xf - -C "${target_dir}"
[[ -s "${target_dir}/postgres.dump" ]] || { echo "Recovered backup is missing postgres.dump" >&2; exit 1; }
[[ -s "${target_dir}/media.tar.gz" ]] || { echo "Recovered backup is missing media.tar.gz" >&2; exit 1; }
[[ -s "${target_dir}/SHA256SUMS" ]] || { echo "Recovered backup is missing SHA256SUMS" >&2; exit 1; }
(cd "${target_dir}" && sha256sum -c SHA256SUMS >/dev/null)
tar -tzf "${target_dir}/media.tar.gz" >/dev/null
chmod 600 "${target_dir}/postgres.dump" "${target_dir}/media.tar.gz" "${target_dir}/SHA256SUMS"
echo "AuRoom encrypted off-site backup recovered: ${target_dir}"
