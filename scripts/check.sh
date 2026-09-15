#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker run --rm -v "$PWD:/workspace:ro" morrowsql-builder:8.4.11-1 \
  bash -c 'for script in scripts/*.sh docker/*.sh; do bash -n "$script" || exit; done'
helm lint charts/morrowsql --kube-version 1.35.6 -f tests/ci-values.yaml
helm template morrowsql charts/morrowsql --kube-version 1.35.6 -f tests/ci-values.yaml >/dev/null
if [[ -d charts/morrowsql-operator ]]; then
  helm lint charts/morrowsql-operator --namespace morrowsql-system --set disableLookups=true
fi
git diff --check
