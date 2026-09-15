#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build dist artifacts
python=${PYTHON:-python3.12}
command -v "$python" >/dev/null || python=python3
"$python" scripts/fetch-sources.py

build_args=()
run_args=()
ca_file=${BUILD_CA_FILE:-}
[[ -n "$ca_file" || ! -f .cache/build-ca.pem ]] || ca_file="$PWD/.cache/build-ca.pem"
if [[ -n "$ca_file" ]]; then
  build_args+=(--secret "id=build_ca,src=$ca_file")
  run_args+=(-v "$ca_file:/etc/ssl/certs/ca-certificates.crt:ro")
fi
docker build "${build_args[@]}" -f docker/builder.Dockerfile -t morrowsql-builder:8.4.11-1 .
component=${1:-all}
if [[ "$component" == server || "$component" == all ]]; then
  docker run --rm --name "morrowsql-build-server-${BUILD_RUN_ID:-local}" \
    --memory="${BUILD_MEMORY:-6g}" --cpus="${BUILD_CPUS:-3}" \
    -e BUILD_JOBS="${BUILD_JOBS:-2}" -v "$PWD:/workspace" "${run_args[@]}" \
    morrowsql-builder:8.4.11-1 bash scripts/build-server.sh
fi
if [[ "$component" == shell || "$component" == all ]]; then
  docker run --rm --name "morrowsql-build-shell-${BUILD_RUN_ID:-local}" \
    --memory="${BUILD_MEMORY:-6g}" --cpus="${BUILD_CPUS:-3}" \
    -e BUILD_JOBS="${BUILD_JOBS:-2}" -v "$PWD:/workspace" "${run_args[@]}" \
    morrowsql-builder:8.4.11-1 bash scripts/build-shell.sh
fi
if [[ "$component" == images || "$component" == all ]]; then
  mkdir -p build/operator-code
  cp -a .cache/src/operator/mysqloperator build/operator-code/
  docker build "${build_args[@]}" -f docker/server.Dockerfile -t morrowsql:8.4.11-1 .
  docker build "${build_args[@]}" -f docker/router.Dockerfile -t morrowsql-router:8.4.11-1 .
  docker build "${build_args[@]}" -f docker/operator.Dockerfile -t morrowsql-operator:8.4.11-1 .
fi
case "$component" in server|shell|images|all) ;; *) echo 'Expected server, shell, images or all' >&2; exit 2 ;; esac
