# MorrowSQL Operator Chart

Chart version: **1.0.0**. Controller: **MySQL Operator 8.4.9-2.1.11**, built
from commit `da256206a7ed5d2dd4082a6bfd6de8a64b3b6c6e` with MySQL Shell 8.4.9.
The upstream CRDs, RBAC and controller logic are preserved. Distribution changes
set the MorrowSQL image repository and chart identity.

Install this chart once per cluster in a dedicated namespace, before installing
`morrowsql`. It owns cluster-wide MySQL CRDs and watches InnoDBCluster resources.
Do not install alongside another MySQL Operator managing these same resources.

```sh
helm install morrowsql-operator ./charts/morrowsql-operator \
  --namespace morrowsql-system --create-namespace
```

The default controller image is:
`ghcr.io/samuelsupe/morrowsql/8.4.11-1/community-operator:8.4.9-2.1.11`.

For private registry mirrors, set `image.registry`, `image.repository`, and
`envs.imagesDefaultRegistry` / `envs.imagesDefaultRepository` consistently. Set
`image.pullSecrets.enabled=true` and `image.pullSecrets.secretName` for an
existing registry Secret. Never pass database passwords in Helm values.

See [Kubernetes deployment](../../docs/kubernetes.md) for the separate database
chart, production TLS, storage, S3 backups, recovery and PVC retention.

## 中文

先在独立命名空间安装本 Chart，再安装数据库 Chart。控制器沿用官方
MySQL Operator 8.4.9-2.1.11 的逻辑，使用本发行版自建镜像。
本 Chart 注册集群级 CRD 和 RBAC，避免与其他管理相同资源的 MySQL Operator
同时安装。数据库密码及 S3 凭据通过已有 Secret 引用。
