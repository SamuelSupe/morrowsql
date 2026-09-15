# Security review for 8.4.11-1

Review date: 2026-09-15. Each native build also scans the actual runtime images
against the vulnerability database available at build time. The database identity
and scanner results accompany the release evidence.

## Scope

Trivy examines Ubuntu packages and Python distributions. Source-built C++ code
cannot be declared safe solely from that scan: Server, Router and Shell versions
are also checked against the upstream advisories. The SPDX files identify the
source-built components alongside the packages detected in the images.

The [June Community advisory](https://dev.mysql.com/community/security/advisories/2026-06-16/)
and [July Oracle advisory](https://www.oracle.com/security-alerts/cpujul2026.html)
list affected Server and Router versions ending at 8.4.9 and 8.4.10 respectively;
this release builds both components from 8.4.11. The
[August Community advisory](https://dev.mysql.com/community/security/advisories/2026-08-18/)
lists NDB Cluster issues and third-party libssh issues. NDB is disabled in the
build. MySQL Shell links the Ubuntu snapshot's libssh, which is included in the
package scan; Oracle's prebuilt Shell 26.7.0 bundle is not redistributed.

## Dependency fixes

The first image scan found CVE-2026-69244 in aiohttp 3.13.3 and
CVE-2026-44431 / CVE-2026-44432 in urllib3 2.6.3. The distribution pins aiohttp
3.14.3 and urllib3 2.7.0, the reported fixed releases. Operator controller source
is unchanged. Native runtime and HA verification run with the updated packages.

## Known limitation

The June advisory includes **CVE-2026-46869**, CVSS 6.5, affecting Shell's dump/load
functionality through 8.4.9. The plan's Shell 8.4.9 pin retains that upstream
issue; this distribution does not claim it is fixed. Only this release's own
trusted databases and backup objects are in the supported restore workflow.
Do not supply databases or dump objects from untrusted parties. Restrict write
access to the backup bucket and use TLS outside the isolated CI fixture.
Reassess the Shell pin for a subsequent release.

An unexplained high/critical scan finding blocks publication. This review and a
clean scan are bounded evidence, not a guarantee that undisclosed issues do not
exist. The source archive includes the exact Ubuntu source packages, original
Python sdists, Rust crates from cryptography's Cargo.lock, and OpenSSL 4.0.2
corresponding to cryptography's bundled wheel library.
