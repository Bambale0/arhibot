#!/usr/bin/env bash
set -Eeuo pipefail

mode=${1:-CHECK}
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
backend_dir=$(cd -- "${script_dir}/.." && pwd)
cd "${backend_dir}"

[[ "${mode}" == "CHECK" || "${mode}" == "UPDATE" ]] || {
  echo "Usage: $0 [CHECK|UPDATE]" >&2
  exit 2
}
command -v pip-compile >/dev/null || {
  echo "pip-compile is required; install backend dev dependencies first" >&2
  exit 2
}

compile_runtime() {
  local output=$1
  pip-compile pyproject.toml \
    --output-file="${output}" \
    --generate-hashes \
    --quiet \
    --strip-extras \
    --no-header \
    --resolver=backtracking \
    --index-url=https://pypi.org/simple
}

compile_build() {
  local output=$1
  pip-compile pyproject.toml \
    --output-file="${output}" \
    --generate-hashes \
    --quiet \
    --strip-extras \
    --no-header \
    --resolver=backtracking \
    --index-url=https://pypi.org/simple \
    --build-deps-for=wheel \
    --only-build-deps
}

if [[ "${mode}" == "UPDATE" ]]; then
  compile_runtime requirements.lock
  compile_build requirements-build.lock
  echo "Python dependency locks updated"
  exit 0
fi

tmp_dir=$(mktemp -d)
trap 'rm -rf "${tmp_dir}"' EXIT
# Seed temporary outputs with the committed pins. pip-compile reuses existing
# versions unless an explicit upgrade is requested, so CHECK validates that
# pyproject constraints still admit the committed lock instead of drifting
# whenever PyPI publishes a newer transitive dependency.
cp requirements.lock "${tmp_dir}/requirements.lock"
cp requirements-build.lock "${tmp_dir}/requirements-build.lock"
compile_runtime "${tmp_dir}/requirements.lock"
compile_build "${tmp_dir}/requirements-build.lock"
status=0
diff -u requirements.lock "${tmp_dir}/requirements.lock" || status=1
diff -u requirements-build.lock "${tmp_dir}/requirements-build.lock" || status=1
if [[ "${status}" -ne 0 ]]; then
  echo "Python dependency locks are stale; run ./scripts/dependency_locks.sh UPDATE" >&2
  exit "${status}"
fi
echo "Python dependency locks are current"
