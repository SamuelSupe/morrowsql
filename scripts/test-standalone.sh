#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker run --rm -v "$PWD:/workspace" morrowsql-builder:8.4.11-1 \
  cc tests/client.c -Ibuild/stage/opt/morrowsql/include \
  -Lbuild/stage/opt/morrowsql/lib -Wl,-rpath,/opt/morrowsql/lib \
  -lmysqlclient -o build/test-client
python=${PYTHON:-python3.12}
command -v "$python" >/dev/null || python=python3
"$python" tests/standalone.py
