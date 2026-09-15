# Kubernetes deployment

Status: release candidate under validation. These commands target the planned
stable artifacts and become usable when the release is published.

## Requirements

- Kubernetes 1.35 with three worker nodes and an appropriate persistent-volume
  provisioner. Each MySQL member gets its own ReadWriteOnce volume.
- Helm with OCI support and permissions to install the operator CRDs and RBAC.
- No other MySQL Operator installation managing these CRDs. The upstream
  operator uses fixed cluster-level role names and watches the cluster.
- A Secret containing `rootUser`, `rootHost`, `rootPassword`; use `root` and `%`
  for the operator administrator. Keep its password out of Helm values and Git.
- Production TLS Secrets: server and Router keys (`tls.crt`, `tls.key`), and a
  CA Secret with `ca.pem`. Certificates must cover the generated cluster DNS
  names. Clients should verify the CA and service hostname.

## Install the operator and a fresh cluster

```sh
helm install morrowsql-operator \
  oci://ghcr.io/samuelsupe/charts/morrowsql-operator \
  --version 1.0.0 --namespace morrowsql-system --create-namespace

helm install orders oci://ghcr.io/samuelsupe/charts/morrowsql \
  --version 1.0.0 --namespace orders-db --create-namespace \
  --values production-values.yaml
```

An example `production-values.yaml` references existing resources:

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
```

The chart schedules three database members on different worker nodes and two
routers on different worker nodes. The upstream operator creates a disruption
budget allowing at most one database member to be voluntarily unavailable.
Resource requests and limits are configurable; size them for the real workload.

The image registry layout is fixed per distribution release. The operator sees
standard `community-server`, `community-router` and `community-operator` image
names underneath `ghcr.io/samuelsupe/morrowsql/8.4.11-1`. The server digest matches
the standalone MorrowSQL image. Do not override controller-owned Pod images.

## Connect and inspect

```sh
kubectl -n orders-db get innodbcluster orders -w
kubectl -n orders-db get pods,pvc,pdb
kubectl -n orders-db get service orders -o yaml
kubectl -n morrowsql-system logs deployment/mysql-operator
```

Applications use the `orders.orders-db.svc.cluster.local` Router service and its
published read/write or read-only port. Create a separate least-privilege
application account; do not use the operator administrator for application work.

Failover may disconnect clients. A disconnected commit has an unknown outcome,
so retry only with an application-level idempotency key. Losing a majority stops
writes. Never force quorum on two independently writable groups.

## Same-release backup and restore

Enable an S3 profile by setting `backup.enabled`, `backup.bucket`, `backup.prefix`,
`backup.existingSecret`, and optionally `backup.endpoint` and `backup.schedule`.
The S3 Secret follows the upstream operator's `config` and `credentials` file
layout. The endpoint override enables a compatible S3 service such as MinIO.

Request a backup:

```yaml
apiVersion: mysql.oracle.com/v2
kind: MySQLBackup
metadata:
  name: orders-backup
spec:
  clusterName: orders
  backupProfileName: s3
  deleteBackupData: false
```

Wait for the MySQLBackup resource to report completion. A resource existing is
not evidence that a backup succeeded. Record the completed backup directory.

Restore with a **new Helm release name**, the same MorrowSQL release, the S3
settings, `restore.enabled: true` and `restore.prefix` pointing to that completed
backup. Verify schema and application data before connecting an application.
An installation-time restore is not a version upgrade or an import from another
MySQL distribution. The caller is responsible for bucket retention policies.

## Stop and uninstall

Uninstalling a cluster stops its workloads but retains its database PVCs. Confirm
backups and storage provisioner reclaim policies before any explicit PVC deletion.
Do not delete the namespace or operator CRDs as a routine shutdown procedure.
Do not uninstall the shared operator while clusters still depend on it.

This release documents fresh installation, same-release restarts, failure
recovery and same-release restore only. Database or operator version upgrades,
Helm rollback as a data-recovery mechanism, and cross-version recovery are not
supported.

## Evidence boundary

CI uses a control-plane node and three worker containers on one native runner.
This exercises kubelet, networking and group-membership failures in simulation.
It does not establish physical host, storage-array or availability-zone isolation.
The local single-node OrbStack cluster is only a development environment.
