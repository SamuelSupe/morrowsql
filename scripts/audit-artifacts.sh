#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
scanner=aquasec/trivy:0.69.3@sha256:bcc376de8d77cfe086a917230e818dc9f8528e3c852f7b1aff648949b6258d1c
mkdir -p artifacts/audit .cache/trivy
failed=0
for component in morrowsql morrowsql-router morrowsql-operator; do
  args=(--rm -v /var/run/docker.sock:/var/run/docker.sock
    -v "$PWD/artifacts/audit:/output" -v "$PWD/.cache/trivy:/root/.cache/trivy")
  if [[ -f .cache/build-ca.pem ]]; then
    args+=(-v "$PWD/.cache/build-ca.pem:/etc/ssl/certs/ca-certificates.crt:ro")
  fi
  docker run "${args[@]}" "$scanner" image --format spdx-json \
    --output "/output/${component}.spdx.json" "${component}:8.4.11-1"
  docker run "${args[@]}" "$scanner" image --scanners vuln --severity HIGH,CRITICAL \
    --exit-code 1 --format json --output "/output/${component}-vulnerabilities.json" \
    "${component}:8.4.11-1" || failed=1
  docker run --rm --entrypoint bash "${component}:8.4.11-1" -c '
    find /opt -type f \( -name "*.so*" -o -perm /111 \) -print0 |
      while IFS= read -r -d "" path; do ldd "$path" 2>/dev/null || true; done
  ' > "artifacts/audit/${component}-libraries.txt"
  if grep -q 'not found' "artifacts/audit/${component}-libraries.txt"; then
    echo "Unresolved shared libraries in $component" >&2
    failed=1
  fi
done
exit "$failed"
