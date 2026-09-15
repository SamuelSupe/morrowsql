# Release validation

Candidate progress is recorded in [native verification](https://github.com/SamuelSupe/morrowsql/actions/workflows/build.yml).
The authoritative report for a published version is its `validation.json`,
`validation.md`, and architecture-specific evidence archives in
[GitHub Releases](https://github.com/SamuelSupe/morrowsql/releases).
No release is established by this source document alone.

| Gate, on both native architectures | Evidence |
| --- | --- |
| Build Server, Router and Shell from the corresponding source archive | Native workflow logs and build attestations |
| Applicable unit tests and four MTR suites | `upstream/unit.xml`, `upstream/mtr.xml`, MTR logs and skip reasons |
| Fresh standalone and Ubuntu archive, TLS, authentication, prepared statements, transactions | Two `standalone-*/results.json` files |
| Restart, crash recovery and same-release backup/restore | Standalone scenario results |
| Three members, two Routers, faults, partitions, maintenance, PVC retention | `morrowsql-*/results.json` and cluster diagnostics |
| S3 failure, one-time and scheduled backup, fresh same-release restore | HA scenarios and MySQLBackup status |
| Runtime dependencies, corresponding sources, SPDX, vulnerabilities | `audit/`, source lock files and [security review](security-review.md) |
| Anonymous downloads, pulls, tags and fresh standalone/Kubernetes installation | [Publication workflow](https://github.com/SamuelSupe/morrowsql/actions/workflows/publish.yml) public-install jobs |

Helm lint and rendering are static checks; they are not cluster runtime evidence.
The local OrbStack cluster has one arm64 node. The release HA gate uses isolated
multi-node CI simulations. The 120-second write-recovery target applies only to
the specified single-member-failure fixture, not to production workloads.

No migration, version upgrade or fixed-duration two-hour soak is required.
The explicit MTR scope exclusions are listed in [mtr-excluded.txt](../tests/mtr-excluded.txt).
MTR also reports upstream-disabled cases and cases requiring debug binaries or
the optional big-test mode. Published reports retain those skip reasons.
The test configuration uses the distribution's `innodb_numa_interleave=OFF`
default, including servers restarted by clone recovery; unprivileged containers
do not require a NUMA memory-policy capability.
Unexplained failures, lost acknowledged transactions, two writable primaries,
unintended PVC deletion or an unresolved confirmed high-severity vulnerability
prevent stable publication.
