#!/usr/bin/env python3
"""Resolve the exact Ubuntu source packages installed in the release images."""
import concurrent.futures
import hashlib
import json
import os
import pathlib
import ssl
import subprocess
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
API = "https://api.launchpad.net/1.0/ubuntu/+archive/primary"
CONTEXT = ssl.create_default_context(cafile=os.environ.get("BUILD_CA_FILE"))
manifest = ROOT / "runtime-sources.json"
previous = {(item["package"], item["version"]): item
            for item in json.loads(manifest.read_text())} if manifest.exists() else {}


def read(url):
    with urllib.request.urlopen(url, context=CONTEXT, timeout=120) as response:
        return response.read()


def resolve(package):
    if package in previous:
        return previous[package]
    name, version = package
    query = urllib.parse.urlencode({"ws.op": "getPublishedSources", "source_name": name,
        "version": version, "exact_match": "true", "distro_series": "https://api.launchpad.net/1.0/ubuntu/noble"})
    publications = json.loads(read(API + "?" + query))["entries"]
    if not publications:
        raise RuntimeError(f"No Ubuntu source publication for {name}={version}")
    urls = json.loads(read(publications[0]["self_link"] + "?ws.op=sourceFileUrls"))
    dsc_url = next(url for url in urls if url.endswith(".dsc"))
    dsc = read(dsc_url)
    checksums = {}
    in_checksums = False
    for line in dsc.decode().splitlines():
        if line == "Checksums-Sha256:":
            in_checksums = True
        elif in_checksums and line.startswith(" "):
            digest, size, filename = line.split()
            checksums[filename] = digest
        else:
            in_checksums = False
    dsc_name = pathlib.PurePosixPath(urllib.parse.urlparse(dsc_url).path).name
    checksums[dsc_name] = hashlib.sha256(dsc).hexdigest()
    files = []
    for url in urls:
        filename = pathlib.PurePosixPath(urllib.parse.urlparse(url).path).name
        files.append({"filename": filename, "url": url, "sha256": checksums[filename]})
    assert len(files) == len(checksums), f"Incomplete source publication: {name}"
    print(f"Resolved {name}={version}", flush=True)
    return {"package": name, "version": version, "publication": publications[0]["self_link"],
            "files": sorted(files, key=lambda item: item["filename"])}


def main():
    packages = set()
    base = (ROOT / "docker/server.Dockerfile").read_text().splitlines()[0].split()[1]
    images = [name + ":8.4.11-1" for name in ("morrowsql", "morrowsql-router", "morrowsql-operator")]
    # Base packages and the CA bootstrap archive remain in earlier OCI layers,
    # including when an apt upgrade replaces their visible runtime versions.
    packages.add(("ca-certificates", "20240203"))
    for image in [base, *images]:
        output = subprocess.check_output(["docker", "run", "--rm", "--entrypoint", "dpkg-query",
            image, "-W", "-f=${source:Package}\t${source:Version}\n"], text=True)
        packages.update(tuple(line.split("\t")) for line in output.splitlines())
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        sources = list(pool.map(resolve, sorted(packages)))
    (ROOT / "runtime-sources.json").write_text(json.dumps(sources, indent=2) + "\n")


if __name__ == "__main__":
    main()
