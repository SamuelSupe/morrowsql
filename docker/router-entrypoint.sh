#!/usr/bin/env bash
set -euo pipefail
umask 077
[[ ${1:-} != mysqlrouter ]] || shift
if [[ -z ${MYSQL_HOST:-} ]]; then exec mysqlrouter "$@"; fi
: "${MYSQL_USER:?MYSQL_USER is required}"
: "${MYSQL_PASSWORD:?MYSQL_PASSWORD is required}"

options=()
while IFS= read -r -d '' value; do options+=("$value"); done < <(
  python3 -c 'import os,shlex,sys; sys.stdout.buffer.write(b"\0".join(s.encode() for s in shlex.split(os.environ.get("MYSQL_ROUTER_BOOTSTRAP_EXTRA_OPTIONS", ""))) + b"\0")'
)
[[ ${options[0]:-} != '' ]] || options=()
for ((attempt=0; attempt<60; attempt++)); do
  if printf '%s\n' "$MYSQL_PASSWORD" | mysqlrouter \
    --bootstrap "$MYSQL_USER@$MYSQL_HOST:${MYSQL_PORT:-3306}" \
    --directory=/tmp/mysqlrouter --force \
    --account="$MYSQL_USER" --account-create=never "${options[@]}"; then
    unset MYSQL_PASSWORD
    exec mysqlrouter --config=/tmp/mysqlrouter/mysqlrouter.conf "$@"
  fi
  sleep 2
done
echo 'MorrowSQL Router bootstrap failed' >&2
exit 1
