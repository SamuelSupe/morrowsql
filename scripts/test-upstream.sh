#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p artifacts/upstream
docker run --rm --name "morrowsql-upstream-${BUILD_RUN_ID:-local}" \
  --memory="${TEST_MEMORY:-6g}" --cpus="${TEST_CPUS:-3}" \
  -e TEST_JOBS="${TEST_JOBS:-2}" -v "$PWD:/workspace" \
  morrowsql-builder:8.4.11-1 bash -euo pipefail -c '
    ctest --test-dir build/server --output-on-failure --parallel "$TEST_JOBS" \
      --output-junit /workspace/artifacts/upstream/unit.xml
    cd build/server/mysql-test
    perl mysql-test-run.pl --suite=main,innodb,rpl,group_replication \
      --parallel="$TEST_JOBS" --force --retry=0 \
      --vardir=/workspace/build/mtr-var \
      --xml-report=/workspace/artifacts/upstream/mtr.xml
  ' 2>&1 | tee artifacts/upstream/run.log
