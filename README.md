# MorrowSQL

[中文](README.zh-CN.md)

An independently built distribution of MySQL Community 8.4, with fresh standalone
deployment and an InnoDB Cluster deployment for Kubernetes.

Release availability and evidence: [GitHub Releases](https://github.com/SamuelSupe/morrowsql/releases).
A version is supported only after its native verification gates and public
installation checks pass. Until the first tagged release is present, this
repository is a release candidate under development.

## Distribution

- Target release: **8.4.11-1**, upstream MySQL **8.4.11**.
- Native Linux amd64 and arm64 builds; binary archives target Ubuntu 24.04.
- Kubernetes target: **1.35**, three database members and two MySQL Routers.
- Server kernel unchanged; `@@version_comment` identifies MorrowSQL.
- Fresh initialization and same-release recovery only. Migration from another
  distribution, version upgrades, and cross-version recovery are unsupported.

The distribution uses upstream MySQL Operator 8.4.9-2.1.11 and MySQL Shell 8.4.9.
The operator controller is reused without modification. Each component retains
its own license and attribution; see [licenses](licenses/).

## Build

Requirements: Docker with Linux containers, Python 3.12 or newer, and enough space
for the source tree and compiler output. Helm is needed for chart checks.

```sh
bash scripts/build.sh all
make check
```

Sources and archive hashes are pinned in [release.json](release.json). Build images
use an Ubuntu snapshot dated 2026-09-14. `BUILD_JOBS`, `BUILD_CPUS` and
`BUILD_MEMORY` control build resource use. `BUILD_CA_FILE` optionally supplies a
trusted CA bundle using a temporary BuildKit secret; it is not included in images.
The corresponding source archive also includes the Ubuntu runtime source
packages, Python sdists and bundled cryptography dependencies, all hash-pinned.

## Run a fresh standalone instance

After the release is published:

```sh
openssl rand -base64 32 > /tmp/morrowsql-root-password
chmod 600 /tmp/morrowsql-root-password
docker volume create morrowsql-data
docker run -d --name morrowsql \
  -v morrowsql-data:/var/lib/mysql \
  -v /tmp/morrowsql-root-password:/run/secrets/root-password:ro \
  -e MYSQL_ROOT_PASSWORD_FILE=/run/secrets/root-password \
  ghcr.io/samuelsupe/morrowsql:8.4.11-1
```

The root account is local to the server by default. To create an application
account during initialization, provide `MYSQL_DATABASE`, `MYSQL_USER` and
`MYSQL_PASSWORD_FILE` together. Passwords also support their plain environment
variable form, but setting both forms is rejected. Database names accept 1-64
ASCII letters, digits or underscores.

Initialization runs with networking disabled. A completed initialization marker
is written only after the temporary server has shut down successfully. An
incomplete nonempty data directory is never silently reinitialized.

## Kubernetes

Ubuntu archive instructions are in [binary installation](docs/binary.md).

See [Kubernetes deployment](docs/kubernetes.md). Production scheduling requires
three worker nodes, independent persistent volumes and TLS credentials. A single
machine running several test nodes is a simulation, not physical fault isolation.

Applications connect through Router. A failover can interrupt connections and
transactions; callers must reconnect and resolve unknown transaction outcomes
with an idempotency key. Quorum loss stops writes rather than forcing a new group.

## Release verification

A stable release must include SHA-256 checksums, corresponding sources, an SPDX
software bill of materials, build attestations and results for both architectures.
The supported scenarios and evidence belong in [validation](docs/validation.md).

No migration, version upgrade or fixed two-hour soak is part of the release gate.
Released files and versioned image tags are never overwritten.

## Licensing and security

MorrowSQL distribution scripts are GPL-2.0-only. MySQL Server and Shell retain
their GPLv2 licenses and additional permissions; the MySQL Operator retains UPL
1.0. Bundled dependencies retain their licenses. MorrowSQL is a third-party
distribution and is not an Oracle product.

See [SECURITY.md](SECURITY.md) for reporting a vulnerability.
The release's scan coverage and known Shell limitation are recorded in
[security review](docs/security-review.md).
