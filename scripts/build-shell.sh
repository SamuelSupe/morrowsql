#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
jobs=${BUILD_JOBS:-2}
cmake -S .cache/src/antlr/runtime/Cpp -B build/antlr -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/opt/antlr \
  -DCMAKE_POSITION_INDEPENDENT_CODE=ON -DANTLR_BUILD_CPP_TESTS=OFF \
  -DWITH_DEMO=OFF
cmake --build build/antlr --target antlr4_static --parallel "$jobs"
mkdir -p /opt/antlr/lib /opt/antlr/include/antlr4-runtime
cp .cache/src/antlr/runtime/Cpp/dist/libantlr4-runtime.a /opt/antlr/lib/
rsync -a --include='*/' --include='*.h' --exclude='*' \
  .cache/src/antlr/runtime/Cpp/runtime/src/ /opt/antlr/include/antlr4-runtime/
cmake -S .cache/src/shell -B build/shell -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/opt/morrowsql-shell \
  -DBUNDLED_ANTLR_DIR=/opt/antlr \
  -DMYSQL_SOURCE_DIR="$PWD/.cache/src/server" \
  -DMYSQL_BUILD_DIR="$PWD/build/server" \
  -DHAVE_PYTHON=ON -DUSE_PYTHON_VERSION=3.12 \
  -DWITH_SSL=system -DWITH_LTO=OFF
cmake --build build/shell --parallel "$jobs"
DESTDIR="$PWD/build/stage" cmake --install build/shell
