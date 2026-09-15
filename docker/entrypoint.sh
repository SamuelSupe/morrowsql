#!/usr/bin/env bash
set -euo pipefail
umask 077

fail() { printf 'MorrowSQL: %s\n' "$*" >&2; exit 1; }

file_env() {
  local key=$1 file_key="${1}_FILE"
  if [[ -v "$key" && -v "$file_key" ]]; then
    fail "set either $key or $file_key, not both"
  fi
  if [[ -v "$file_key" ]]; then
    [[ -r "${!file_key}" ]] || fail "cannot read $file_key"
    export "$key=$(cat -- "${!file_key}")"
  fi
  unset "$file_key"
}

[[ ${1:-} == -* ]] && set -- mysqld "$@"
[[ ${1:-} == mysqld ]] || exec "$@"
for arg in "$@"; do
  case "$arg" in --help|--version|-V|'-?') exec "$@" ;; esac
done

for key in MYSQL_ROOT_PASSWORD MYSQL_PASSWORD; do file_env "$key"; done
config=$("$@" --verbose --help 2>/dev/null) || fail 'invalid server configuration'
datadir=$(awk '$1 == "datadir" {print $2; exit}' <<< "$config")
[[ -n "$datadir" ]] || fail 'could not determine datadir'
mkdir -p "$datadir" /var/run/mysqld /var/lib/mysql-files

if [[ $(id -u) == 0 ]]; then
  chown mysql:mysql "$datadir" /var/run/mysqld /var/lib/mysql-files
  exec setpriv --reuid=mysql --regid=mysql --init-groups "$0" "$@"
fi

if [[ -f "$datadir/.morrowsql-initialized" ]]; then
  [[ -d "$datadir/mysql" ]] || fail 'initialized data directory is incomplete'
  [[ $(cat "$datadir/.morrowsql-initialized") == $(cat /usr/local/share/morrowsql/version) ]] || fail 'data directory belongs to a different MorrowSQL release'
  [[ ${MYSQL_INITIALIZE_ONLY:-0} == 1 ]] && exit 0
  unset MYSQL_ROOT_PASSWORD MYSQL_PASSWORD
  exec "$@"
fi

# A failed initialization must never be treated as an existing usable database.
if find "$datadir" -mindepth 1 -maxdepth 1 ! -name lost+found -print -quit | read -r _; then
  fail 'data directory is not empty and has no completed MorrowSQL initialization'
fi
[[ -n ${MYSQL_ROOT_PASSWORD:-} ]] || fail 'MYSQL_ROOT_PASSWORD or MYSQL_ROOT_PASSWORD_FILE is required for initialization'
if [[ -n ${MYSQL_USER:-} || -n ${MYSQL_PASSWORD:-} ]]; then
  [[ -n ${MYSQL_USER:-} && -n ${MYSQL_PASSWORD:-} && -n ${MYSQL_DATABASE:-} ]] || fail 'MYSQL_USER, MYSQL_PASSWORD and MYSQL_DATABASE must be set together'
  [[ $MYSQL_USER != root ]] || fail 'MYSQL_USER must not be root'
fi

temporary=$(mktemp -d)
server_pid=
cleanup() {
  if [[ -n "$server_pid" ]] && kill -0 "$server_pid" 2>/dev/null; then
    kill -TERM "$server_pid"
    wait "$server_pid" || true
  fi
  rm -rf -- "$temporary"
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

"$@" --initialize-insecure
"$@" --skip-networking --mysqlx=OFF --socket="$temporary/mysql.sock" \
  --pid-file="$temporary/mysql.pid" --log-error="$temporary/server.log" &
server_pid=$!
ready=0
for ((attempt=0; attempt<300; attempt++)); do
  if mysql --no-defaults --protocol=socket --socket="$temporary/mysql.sock" -uroot -e 'SELECT 1' >/dev/null 2>&1; then
    ready=1
    break
  fi
  kill -0 "$server_pid" 2>/dev/null || fail 'initialization server exited; data directory requires inspection'
  sleep 1
done
[[ $ready == 1 ]] || fail 'initialization server did not become ready within 300 seconds'

python3 /usr/local/lib/morrowsql/bootstrap.py "$temporary"
mysql --no-defaults --protocol=socket --socket="$temporary/mysql.sock" -uroot < "$temporary/bootstrap.sql"
for sql in /docker-entrypoint-initdb.d/*.sql; do
  [[ -f "$sql" ]] || continue
  mysql --defaults-extra-file="$temporary/client.cnf" --protocol=socket --socket="$temporary/mysql.sock" < "$sql"
done
kill -TERM "$server_pid"
wait "$server_pid"
server_pid=
printf '%s\n' "$(cat /usr/local/share/morrowsql/version)" > "$datadir/.morrowsql-initialized"
cleanup
trap - EXIT TERM INT
[[ ${MYSQL_INITIALIZE_ONLY:-0} == 1 ]] && exit 0
unset MYSQL_ROOT_PASSWORD MYSQL_PASSWORD
exec "$@"
