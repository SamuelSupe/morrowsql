#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
jobs=${BUILD_JOBS:-2}
cmake -S .cache/src/antlr/runtime/Cpp -B build/antlr -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/opt/antlr \
  -DCMAKE_POSITION_INDEPENDENT_CODE=ON -DANTLR_BUILD_CPP_TESTS=OFF \
  -DANTLR_BUILD_SHARED=OFF -DANTLR_BUILD_STATIC=ON -DWITH_DEMO=OFF
cmake --build build/antlr --parallel "$jobs"
cmake --install build/antlr
cmake -S .cache/src/shell -B build/shell -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/opt/morrowsql-shell \
  -DCMAKE_PREFIX_PATH=/opt/antlr \
  -DMYSQL_SOURCE_DIR="$PWD/.cache/src/server" \
  -DMYSQL_BUILD_DIR="$PWD/build/server" \
  -DHAVE_PYTHON=ON -DUSE_PYTHON_VERSION=3.12 \
  -DWITH_SSL=system -DWITH_LTO=OFF
cmake --build build/shell --parallel "$jobs"
DESTDIR="$PWD/build/stage" cmake --install build/shell
