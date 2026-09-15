# Kubernetes 部署、备份与恢复

[English](kubernetes.md)

**当前处于发行验证阶段，以下公开镜像和 OCI Chart 命令将在正式发布后可用。**
本版只支持全新部署，以及 MorrowSQL 8.4.11-1 内的运行、故障恢复和备份还原。

## 部署条件

- Kubernetes 1.35，至少三个工作节点，提供持久卷的 StorageClass。
- 三个数据库成员各使用独立的 ReadWriteOnce PVC，并严格分散到不同节点。
- Helm 能安装 OCI Chart；安装 Operator 的账号具备注册 CRD 和 RBAC 的权限。
- 同一集群中不运行其他管理这些 MySQL CRD 的 Operator。
- 预先创建管理员 Secret 和生产 TLS 证书 Secret。

生产证书需要覆盖实际使用的服务 DNS 名称。以 `orders` 集群、`orders-db`
命名空间和默认 `cluster.local` 域为例，数据库证书应覆盖成员地址
`orders-0.orders-instances.orders-db.svc.cluster.local` 等；可以使用
`*.orders-instances.orders-db.svc.cluster.local`，并包含成员服务地址。
Router 证书需要覆盖客户端实际连接的
`orders.orders-db.svc.cluster.local`。客户端应校验 CA 和服务名。

## 准备凭据

将管理员密码保存在受保护的文件中，通过文件创建 Secret，避免密码进入命令行：

```sh
kubectl create namespace orders-db
kubectl -n orders-db create secret generic orders-administrator \
  --from-literal=rootUser=root --from-literal=rootHost=% \
  --from-file=rootPassword=/secure/orders-root-password

kubectl -n orders-db create secret generic orders-ca --from-file=ca.pem=/secure/ca.pem
kubectl -n orders-db create secret tls orders-server-tls \
  --cert=/secure/server.crt --key=/secure/server.key
kubectl -n orders-db create secret tls orders-router-tls \
  --cert=/secure/router.crt --key=/secure/router.key
```

`rootUser`、`rootHost`、`rootPassword` 是 Operator 管理员 Secret 的三个固定键。
管理员用于集群管理；业务连接应使用单独授权的应用账号。

## 安装

先安装 Operator，再安装数据库集群：

```sh
helm install morrowsql-operator \
  https://github.com/SamuelSupe/morrowsql/releases/download/v8.4.11-1/morrowsql-operator-1.0.0.tgz \
  -n morrowsql-system --create-namespace

helm install orders https://github.com/SamuelSupe/morrowsql/releases/download/v8.4.11-1/morrowsql-1.0.0.tgz \
  -n orders-db -f production-values.yaml
```

`production-values.yaml` 示例：

```yaml
credentials:
  existingSecret: orders-administrator
storage:
  className: your-storage-class
  size: 100Gi
tls:
  caSecret: orders-ca
  serverSecret: orders-server-tls
  routerSecret: orders-router-tls
resources:
  requests:
    cpu: "1"
    memory: 2Gi
  limits:
    cpu: "2"
    memory: 4Gi
```

资源配额应根据实际负载调整。`nodeSelector`、`tolerations` 用于调度约束；数据库
成员保留严格节点反亲和，两个 Router 也分布于不同节点。上游 Operator 创建
`maxUnavailable: 1` 的 PDB；对于固定的三个成员，它要求正常维护时至少保留两个。

默认 Service 为 ClusterIP，数据库与 Router 要求 TLS。仅测试可配置
`tls.selfSigned: true` 使用自签名证书；生产部署使用上述证书 Secret。
镜像在发行版目录下固定命名，不要手工修改 Operator 管理的 Pod 镜像。

## 查看状态与连接

```sh
kubectl -n orders-db get innodbcluster orders -w
kubectl -n orders-db get pods,pvc,pdb
kubectl -n orders-db get service orders -o yaml
kubectl -n morrowsql-system logs deployment/mysql-operator
```

业务通过 Router 服务连接。默认 MySQL 协议读写入口为 6446，只读入口为 6447；
以 Service 实际公布的端口为准。连接时使用 `VERIFY_IDENTITY` 校验 TLS 服务名。

主库故障后会选主，连接和正在执行的事务可能中断。应用需要重连；若在提交时断线，
事务结果可能未知，应使用业务幂等键查询或重试。失去多数成员后停止写入，不自动
强制恢复仲裁，也不要将少数派人为提升为独立可写集群。

## S3 备份

创建包含 `config` 和 `credentials` 两个文件的 Secret：

```sh
kubectl -n orders-db create secret generic orders-s3 \
  --from-file=config=/secure/aws-config \
  --from-file=credentials=/secure/aws-credentials
```

配置文件采用 AWS profile 格式。`config` 的 `[default]` 中设置 `region`；
`credentials` 的 `[default]` 中设置 `aws_access_key_id` 和
`aws_secret_access_key`。文件和 Secret 应受到访问控制。

安装时在 values 中启用备份：

```yaml
backup:
  enabled: true
  bucket: orders-backups
  prefix: orders
  existingSecret: orders-s3
  profile: default
  endpoint: https://your-s3-compatible-endpoint
  schedule: "0 2 * * *"
```

`endpoint` 用于 S3 兼容服务；使用 AWS 默认端点时可省略。`schedule` 可省略，只使用
一次性备份。创建一次性备份资源：

```yaml
apiVersion: mysql.oracle.com/v2
kind: MySQLBackup
metadata:
  name: orders-backup
  namespace: orders-db
spec:
  clusterName: orders
  backupProfileName: s3
  deleteBackupData: false
```

```sh
kubectl -n orders-db get mysqlbackup orders-backup -o yaml
```

必须等到 `status.status: Completed`，并记录 `status.output`。资源创建成功不代表
备份成功；失败会在状态和备份任务日志中显示。桶的保留策略由使用者配置。

## 同版本还原

选择新的 Helm release 名称，并使用同一版 MorrowSQL 8.4.11-1。提供 S3 配置，设置：

```yaml
restore:
  enabled: true
  prefix: orders/<completed-backup-output>
```

`restore.prefix` 是完整备份目录，即备份的 `backup.prefix` 加上完成状态中的
`status.output`。为新集群准备覆盖其 DNS 名称的 TLS 证书和管理员 Secret。
待三个新成员上线后，核对表结构、数据以及应用约束，再接入业务。
新集群使用安装 Secret 中的管理员凭据；上游还原默认不加载应用账号，需要另行
重建并验证应用账号的授权，然后再接入业务流量。
不得将该流程用于跨版本还原或外部 MySQL 数据迁入。

## 卸载与数据保留

```sh
helm uninstall orders -n orders-db
kubectl -n orders-db get pvc
```

卸载集群保留 PVC。删除数据需要另行显式删除 PVC，并核对存储后端的回收策略。
不要将删除命名空间、删除 Operator CRD 或 Helm rollback 当作日常停机、升级或
数据恢复手段。仍有集群依赖时，不要卸载共享 Operator。

## 验证范围

发布门槛在两个原生架构的 CI 中使用一个控制平面和三个工作节点容器，覆盖选主、
节点失联、网络分区、Router/Operator 重启、PVC 保留和 S3 同版本还原。
这是多节点模拟环境，不能证明物理主机、存储阵列或可用区隔离。
单成员故障后 120 秒内恢复写入是该 CI 环境的验收目标，不是生产 SLA。
