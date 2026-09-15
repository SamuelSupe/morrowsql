# Ubuntu 24.04 二进制包安装

[English](binary.md)

选择与机器原生架构一致的 `amd64` 或 `arm64` 包，先核对 SHA-256 和发行构建证明。
包中包含 Server、命令行客户端及 Router；Kubernetes 使用独立的配套镜像。
当前正式二进制发行仍在验证中。

## 安装运行库

```sh
sudo apt-get update
sudo apt-get install libssl3t64 libaio1t64 libnuma1 libncurses6 libtinfo6 \
  libtirpc3t64 libstdc++6 libudev1 libldap2 libsasl2-2 libcurl4t64 \
  libevent-2.1-7t64 liblz4-1 libzstd1
```

将压缩包解压到 `/opt/morrowsql`，创建专用的非 root 运行账号和空数据目录
`/var/lib/morrowsql`，将目录归属设为该账号。将包中的 `my.cnf.example` 复制为
`/etc/morrowsql.cnf`，检查其中的绝对路径。后续数据库命令均以该专用账号运行。
默认只监听回环地址，并要求 TCP 连接使用 TLS。

## 全新初始化

```sh
export PATH=/opt/morrowsql/bin:/opt/morrowsql/sbin:$PATH
mysqld --defaults-file=/etc/morrowsql.cnf --initialize-insecure
mysqld --defaults-file=/etc/morrowsql.cnf --skip-networking --mysqlx=OFF &
MYSQL_HISTFILE=/dev/null mysql --defaults-file=/etc/morrowsql.cnf -uroot
```

在这次本地交互式 SQL 会话中设置密码，然后停止临时实例：

```sql
ALTER USER 'root'@'localhost' IDENTIFIED BY '<你的强密码>';
SHUTDOWN;
```

此时网络监听关闭，只能通过本地 socket 连接。不要将真实密码写入 shell 命令行，
并在执行凭据语句时保持 MySQL 历史记录关闭。初始化只用于空目录，不能重新初始化
已有目录，也不能直接使用其他发行版或版本的数据目录。

## 启动、连接与停止

```sh
mysqld --defaults-file=/etc/morrowsql.cnf &
mysql --defaults-file=/etc/morrowsql.cnf -uroot -p
mysqladmin --defaults-file=/etc/morrowsql.cnf -uroot -p shutdown
```

单独的 `-p` 会以不回显的方式提示输入密码。重启时保留相同配置与数据目录。
通过 `SELECT @@version, @@version_comment;` 核对 `8.4.11` 和
`MorrowSQL 8.4.11-1`。若需远程访问，应明确配置监听地址、生产 TLS 证书以及
独立应用账号，客户端使用 `--ssl-mode=VERIFY_IDENTITY --ssl-ca=/path/to/ca.pem`。

## 自身备份和同版本还原

```sh
umask 077
mysqldump --defaults-file=/etc/morrowsql.cnf -uroot -p \
  --single-transaction --routines --events --triggers \
  --set-gtid-purged=OFF --databases application > application.sql
mysql --defaults-file=/etc/fresh-morrowsql.cnf -uroot -p < application.sql
```

还原目标必须是全新初始化的 MorrowSQL 8.4.11-1 实例。`--single-transaction` 只为
事务型 InnoDB 表提供一致快照；备份期间的结构变更和非事务表需要另外协调。
应用账号需要单独重建。还原后核对表结构、行数和业务不变量，再切换业务连接。
备份文件应受到访问控制。

本版不提供外部 MySQL 迁入、版本升级、跨版本还原或自动时间点恢复。
