#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
archive=${1:?Pass the native binary archive}
temporary=$(mktemp -d "$PWD/build/package-test.XXXXXX")
trap 'rm -rf -- "$temporary"' EXIT
tar -xzf "$archive" -C "$temporary"
directory=$(find "$temporary" -mindepth 1 -maxdepth 1 -type d)
[[ -n "$directory" && -d "$directory/bin" ]]
export MORROWSQL_BINARY_DIRECTORY="$directory"
bash scripts/test-standalone.sh
