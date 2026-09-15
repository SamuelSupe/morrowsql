# Ubuntu 24.04 binary installation

Use the archive matching the machine's native architecture. Verify its SHA-256
against the signed release attestation before extraction. The archive includes
Server, command-line clients and Router. Kubernetes uses the separate images.

Install the shared-library dependencies on Ubuntu 24.04:

```sh
sudo apt-get update
sudo apt-get install libssl3t64 libaio1t64 libnuma1 libncurses6 libtinfo6 \
  libtirpc3t64 libstdc++6 libudev1 libldap2 libsasl2-2 libcurl4t64 \
  libevent-2.1-7t64 liblz4-1 libzstd1
```

Extract into `/opt/morrowsql`. Create a dedicated unprivileged account and an
empty `/var/lib/morrowsql` owned by that account. Copy `my.cnf.example` to
`/etc/morrowsql.cnf`, review its paths, and protect the file from other users.
Run all following database commands as that account. The default configuration
accepts connections on loopback only.

## Initialize and set the first password

```sh
export PATH=/opt/morrowsql/bin:/opt/morrowsql/sbin:$PATH
mysqld --defaults-file=/etc/morrowsql.cnf --initialize-insecure
mysqld --defaults-file=/etc/morrowsql.cnf --skip-networking --mysqlx=OFF &
MYSQL_HISTFILE=/dev/null mysql --defaults-file=/etc/morrowsql.cnf -uroot
```

In that local interactive session, set a strong password:

```sql
ALTER USER 'root'@'localhost' IDENTIFIED BY '<your-secret-password>';
SHUTDOWN;
```

This session uses the local socket while network listeners are disabled. Do not
place the real password in shell arguments or shell history. Keep MySQL history
disabled for credential statements. Initialization is for an empty directory;
never initialize an existing directory or reuse another release's data.

## Start, stop and reconnect

```sh
mysqld --defaults-file=/etc/morrowsql.cnf &
mysql --defaults-file=/etc/morrowsql.cnf -uroot -p
mysqladmin --defaults-file=/etc/morrowsql.cnf -uroot -p shutdown
```

`-p` prompts without echoing the password. Reuse the same configuration and data
directory for restarts. Confirm `SELECT @@version, @@version_comment;` reports
`8.4.11` and `MorrowSQL 8.4.11-1`. For remote access, configure the bind addresses,
TLS certificates and application accounts explicitly. Clients should use
`--ssl-mode=VERIFY_IDENTITY --ssl-ca=/path/to/ca.pem` with user-provided certificates.

## Back up and restore application data

```sh
umask 077
mysqldump --defaults-file=/etc/morrowsql.cnf -uroot -p \
  --single-transaction --routines --events --triggers \
  --set-gtid-purged=OFF --databases application > application.sql
mysql --defaults-file=/etc/fresh-morrowsql.cnf -uroot -p < application.sql
```

Use a freshly initialized **MorrowSQL 8.4.11-1** target. Coordinate schema changes
and nontransactional tables separately: `--single-transaction` provides a
consistent snapshot for transactional InnoDB tables only. Recreate application
accounts separately, check row counts and application-level invariants, then
connect the application to the restored instance. Keep the backup private.

## 二进制包使用范围

仅支持 Ubuntu 24.04 对应原生架构、空目录初始化与同一发行版重启。
先校验压缩包，再按上面的步骤以非 root 用户运行。初始化时关闭网络，
通过本地 socket 设置密码后停止临时实例，再正常启动。
备份还原目标必须是新建的 MorrowSQL 8.4.11-1 实例；还原后核对应用数据。
本版不提供官方 MySQL 迁入、版本升级、跨版本恢复或时间点恢复流程。
