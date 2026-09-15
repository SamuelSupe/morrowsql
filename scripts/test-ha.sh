#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python=${PYTHON:-python3.12}
command -v "$python" >/dev/null || python=python3
"$python" scripts/install-test-tools.py
export PATH="$PWD/.cache/bin:$PATH"
"$python" tests/ha.py
