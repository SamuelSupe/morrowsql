#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
jobs=${BUILD_JOBS:-2}
version=$(python3 -c 'import json; print(json.load(open("release.json"))["version"])')
cmake -S .cache/src/server -B build/server -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=/opt/morrowsql \
  -DINSTALL_LAYOUT=STANDALONE \
  -DCOMPILATION_COMMENT="MorrowSQL ${version}" \
  -DCOMPILATION_COMMENT_SERVER="MorrowSQL ${version}" \
  -DWITH_ROUTER=ON -DWITH_NDB=OFF -DWITH_UNIT_TESTS=ON \
  -DWITH_SSL=system -DWITH_LTO=OFF
cmake --build build/server --parallel "$jobs"
DESTDIR="$PWD/build/stage" cmake --install build/server
cp /build-packages.tsv build/build-packages.tsv
