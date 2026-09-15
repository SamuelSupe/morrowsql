# MorrowSQL

[English](README.md)

基于 MySQL Community 8.4 的自主发行版本，面向全新部署、独立运行和 Kubernetes
InnoDB Cluster 高可用集群。

**首版仍在构建和验证中，尚无通过发布门槛的正式二进制版本。** 功能支持声明以最终
公开的双架构验证报告为准。

## 首版范围

- 发行版本 `8.4.11-1`，上游 MySQL `8.4.11`，保持数据库内核。
- Linux amd64、arm64 原生构建；压缩包支持 Ubuntu 24.04。
- Kubernetes 1.35，3 个数据库成员、2 个 Router、单主写入。
- 全新初始化、持久化重启、故障恢复、自身备份与同版本还原。
- 不提供其他 MySQL 发行版迁入、版本升级和跨版本恢复；不设固定两小时混合负载门槛。

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

- 独立容器启动示例见 [English README](README.md#run-a-fresh-standalone-instance)。
- Kubernetes 部署说明见 [部署文档](docs/kubernetes.md)。
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
