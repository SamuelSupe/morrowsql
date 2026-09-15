# Release validation

Status: **NOT RELEASED — validation in progress**.

| Gate | amd64 | arm64 |
| --- | --- | --- |
| Native source build and dependencies | Not run | In progress |
| Applicable unit tests and MTR suites | Not run | Not run |
| Fresh standalone startup, TLS, authentication, transactions | Not run | Not run |
| Restart, crash recovery, same-release backup and restore | Not run | Not run |
| Three-member Kubernetes cluster and two routers | Not run | Not run |
| Primary/process/pod/node failure and partition handling | Not run | Not run |
| Operator/router recovery, maintenance, PVC retention | Not run | Not run |
| S3 backup failure, success and fresh same-release restore | Not run | Not run |
| Licenses, SBOM, vulnerabilities, source rebuild, attestations | Not run | Not run |
| Anonymous downloads and fresh installation | Not run | Not run |

Helm lint and rendering are static checks; they are not cluster runtime evidence.
The local OrbStack cluster has one arm64 node. The release HA gate uses isolated
multi-node CI simulations. The 120-second write-recovery target applies only to
the specified single-member-failure fixture, not to production workloads.

No migration, version upgrade or fixed-duration two-hour soak is required.
Unexplained failures, lost acknowledged transactions, two writable primaries,
unintended PVC deletion or an unresolved confirmed high-severity vulnerability
prevent stable publication.
