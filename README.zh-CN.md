# MorrowSQL

[English](README.md)

基于 MySQL Community 8.4 的自主发行版本，面向全新部署、独立运行和 Kubernetes
InnoDB Cluster 高可用集群。

版本和验证报告见 [GitHub Releases](https://github.com/SamuelSupe/morrowsql/releases)。
只有通过双架构验证及公开渠道全新安装检查的版本才提供支持。首个标签版本发布前，
本仓库处于候选版本开发阶段。

## 首版范围

- 发行版本 `8.4.11-1`，上游 MySQL `8.4.11`，保持数据库内核。
- Linux amd64、arm64 原生构建；压缩包支持 Ubuntu 24.04。
- Kubernetes 1.35，3 个数据库成员、2 个 Router、单主写入。
- 全新初始化、持久化重启、故障恢复、自身备份与同版本还原。
- 不提供其他 MySQL 发行版迁入、版本升级和跨版本恢复；不设固定两小时混合负载门槛。

完整源码包包含上游组件源码、Ubuntu 运行库源码、Python 源码包及 cryptography
使用的 Rust 和 OpenSSL 源码，均固定版本和 SHA-256。
扫描范围和已知 Shell 限制见[安全审查](docs/security-review.md)。

集群管理复用官方 MySQL Operator 8.4.9-2.1.11，配套 MySQL Shell 8.4.9；通过镜像
启动契约适配 MorrowSQL，不修改 Operator 的仲裁与控制逻辑。

## 源码构建

准备 Docker、Python 3.12 或更新版本和足够的源码、构建空间。检查 Chart 还需要 Helm。

```sh
bash scripts/build.sh all
make check
```

[release.json](release.json) 固定源码提交及归档校验值；构建使用 Ubuntu 固定日期快照。
`BUILD_JOBS`、`BUILD_CPUS`、`BUILD_MEMORY` 控制资源占用。企业网络可通过
`BUILD_CA_FILE` 临时提供可信证书，证书不会写入公开镜像。

## 部署与恢复

正式发布后，可以全新启动独立容器：

```sh
umask 077
openssl rand -base64 32 > /tmp/morrowsql-root-password
docker volume create morrowsql-data
docker run -d --name morrowsql \
  -v morrowsql-data:/var/lib/mysql \
  -v /tmp/morrowsql-root-password:/run/secrets/root-password:ro \
  -e MYSQL_ROOT_PASSWORD_FILE=/run/secrets/root-password \
  ghcr.io/samuelsupe/morrowsql:8.4.11-1
```

初始化应用账号时，同时提供 `MYSQL_DATABASE`、`MYSQL_USER` 和
`MYSQL_PASSWORD_FILE`。数据库名允许 1–64 个 ASCII 字母、数字或下划线。
密码也支持直接使用环境变量，但同一密码的环境变量和 `_FILE` 不能同时设置。

- Ubuntu 二进制包安装见 [安装文档](docs/binary.zh-CN.md)。
- Kubernetes 部署说明见 [部署文档](docs/kubernetes.zh-CN.md)。
- 默认管理员只允许本机连接；应用账号通过初始化变量单独创建。
- 初始化阶段禁止网络连接，成功结束后才记录初始化完成。非空且初始化不完整的目录
  会报错，不自动清除或重建。
- 高可用生产调度需要至少三个工作节点和独立持久卷。连接通过 Router；切换期间应用
  需要重连，并处理结果未知的事务。失去多数成员时停止写入。
- 自身备份恢复到相同发行版本的新实例或新集群，不覆盖现有集群的数据。

## 发布标准

正式版本须附完整对应源码、许可证、SHA-256、SPDX 物料清单、构建证明和双架构
[验证报告](docs/validation.md)。已发布版本不覆盖。CI 多节点故障测试属于模拟环境，
不等同于真实多机或跨可用区验证。

MorrowSQL 是第三方发行版，不是 Oracle 官方产品。各组件保留各自许可证及版权声明，
详见 [许可证目录](licenses/)；安全问题报告方式见 [SECURITY.md](SECURITY.md)。
