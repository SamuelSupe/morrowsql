#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mode=${1:-all}
case "$mode" in unit|mtr|all) ;; *) echo 'Expected unit, mtr or all' >&2; exit 2 ;; esac
mkdir -p artifacts/upstream
name="morrowsql-upstream-$(date +%s)-$$"
volume=$(docker volume create --label morrowsql.test=upstream "$name")
cleanup() {
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker volume rm "$volume" >/dev/null
}
trap cleanup EXIT
# Permission and case-sensitive path tests need a native Linux filesystem and
# an ordinary user, even when the source checkout is on a macOS shared folder.
docker run --rm --name "$name" \
  --memory="${TEST_MEMORY:-6g}" --cpus="${TEST_CPUS:-3}" \
  -e TEST_MODE="$mode" -e TEST_JOBS="${TEST_JOBS:-2}" \
  -e MTR_SUITES="${MTR_SUITES:-main,innodb,rpl,group_replication}" \
  -e CTEST_RERUN_FAILED="${CTEST_RERUN_FAILED:-0}" \
  -v "$PWD:/input:ro" -v "$volume:/workspace" \
  -v "$PWD/artifacts/upstream:/evidence" \
  morrowsql-builder:8.4.11-1 bash -euo pipefail -c '
    mkdir -p /workspace/build/server /workspace/build/results /workspace/.cache/src/server
    cp -a /input/build/server/. /workspace/build/server/
    commit=$(python3 -c '\''import json; print(json.load(open("/input/release.json"))["sources"]["server"]["commit"])'\'')
    tar -xzf "/input/.cache/archives/server-$commit.tar.gz" \
      --strip-components=1 -C /workspace/.cache/src/server
    # Clone tests restart through mysqld_safe, which does not inherit MTR
    # command-line server options. Keep the distribution default in its config.
    printf "\n[mysqld]\ninnodb_numa_interleave=OFF\n" >> \
      /workspace/.cache/src/server/mysql-test/include/default_mysqld.cnf
    chown -R 1000:1000 /workspace
    status=0
    setpriv --reuid=1000 --regid=1000 --init-groups env HOME=/home/ubuntu bash -euo pipefail -c '\''
      if [[ "$TEST_MODE" == unit || "$TEST_MODE" == all ]]; then
        args=()
        [[ "$CTEST_RERUN_FAILED" != 1 ]] || args+=(--rerun-failed)
        ctest --test-dir build/server --output-on-failure --parallel "$TEST_JOBS" \
          --output-junit /workspace/build/results/unit.xml "${args[@]}"
      fi
      if [[ "$TEST_MODE" == mtr || "$TEST_MODE" == all ]]; then
        cd build/server/mysql-test
        perl mysql-test-run.pl --suite="$MTR_SUITES" \
          --skip-test-list=/input/tests/mtr-excluded.txt \
          --mysqld=--innodb-numa-interleave=OFF \
          --parallel="$TEST_JOBS" --force --retry=0 \
          --vardir=/workspace/build/mtr-var \
          --xml-report=/workspace/build/results/mtr.xml
      fi
    '\'' || status=$?
    cp -a /workspace/build/results/. /evidence/
    if [[ -d /workspace/build/mtr-var/log ]]; then
      tar -czf /evidence/mtr-diagnostics.tar.gz -C /workspace/build/mtr-var log
    fi
    exit "$status"
  ' 2>&1 | tee "artifacts/upstream/${mode}-run.log"
