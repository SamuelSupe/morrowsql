#!/usr/bin/env python3
"""Add source-built components and verify runtime source coverage."""
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
release = json.loads((ROOT / "release.json").read_text())
runtime = json.loads((ROOT / "runtime-sources.json").read_text())
available = {(item["package"], item["version"]) for item in runtime}
for component in ("morrowsql", "morrowsql-router", "morrowsql-operator"):
    image = component + ":" + release["version"]
    installed = subprocess.check_output(["docker", "run", "--rm", "--entrypoint", "dpkg-query", image,
        "-W", "-f=${source:Package}\t${source:Version}\n"], text=True)
    packages = {tuple(line.split("\t")) for line in installed.splitlines()}
    missing = packages - available
    if missing:
        raise SystemExit(f"Missing corresponding runtime sources in {image}: {sorted(missing)}")
    destination = ROOT / "artifacts/audit" / (component + ".spdx.json")
    document = json.loads(destination.read_text())
    included = [("server", "MySQL Server and Router", "8.4.11", "GPL-2.0-only")]
    if component == "morrowsql-operator":
        included += [("shell", "MySQL Shell", "8.4.9", "GPL-2.0-only"),
                     ("operator", "MySQL Operator", "8.4.9-2.1.11", "UPL-1.0"),
                     ("antlr", "ANTLR C++ runtime", "4.10.1", "BSD-3-Clause")]
    for key, name, version, license_id in included:
        source = release["sources"][key]
        identifier = "SPDXRef-MorrowSQL-" + key
        document["packages"].append({"SPDXID": identifier, "name": name, "versionInfo": version,
            "downloadLocation": f"https://codeload.github.com/{source['repository']}/tar.gz/{source['commit']}",
            "filesAnalyzed": False, "licenseConcluded": "NOASSERTION", "licenseDeclared": license_id,
            "copyrightText": "NOASSERTION", "sourceInfo": f"Unmodified source commit {source['commit']}; see bundled license and additional permissions",
            "checksums": [{"algorithm": "SHA256", "checksumValue": source["sha256"]}]})
        document.setdefault("relationships", []).append({"spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES", "relatedSpdxElement": identifier})
    destination.write_text(json.dumps(document, indent=2) + "\n")
    (destination.parent / (component + "-runtime-sources.tsv")).write_text(installed)
wheel_ssl = subprocess.check_output(["docker", "run", "--rm", "--entrypoint", "mysqlsh",
    "morrowsql-operator:" + release["version"], "--py", "-e",
    "from cryptography.hazmat.backends.openssl.backend import backend; print(backend.openssl_version_text())"], text=True).strip()
if wheel_ssl != "OpenSSL 4.0.2 25 Aug 2026":
    raise SystemExit("Unexpected cryptography wheel OpenSSL; corresponding source must be updated: " + wheel_ssl)
(ROOT / "artifacts/audit/cryptography-openssl.txt").write_text(wheel_ssl + "\n")
