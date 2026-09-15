#!/usr/bin/env python3
"""Promote the verified image bytes without rebuilding or replacing a release tag."""
import hashlib
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
VERSION = "8.4.11-1"
PREFIX = "ghcr.io/samuelsupe/morrowsql"
TARGETS = {
    "morrowsql": PREFIX + ":" + VERSION,
    "community-server": PREFIX + "/" + VERSION + "/community-server:8.4.11",
    "community-router": PREFIX + "/" + VERSION + "/community-router:8.4.11",
    "community-operator": PREFIX + "/" + VERSION + "/community-operator:8.4.9-2.1.11",
}


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def manifest(reference):
    return json.loads(run("docker", "buildx", "imagetools", "inspect", reference, "--format", "{{json .Manifest}}"))


def main():
    run_id = sys.argv[1]
    assert run_id.isdecimal()
    output = ROOT / "dist/public"
    report = json.loads((output / "validation.json").read_text())
    assert report["verificationRun"].endswith("/" + run_id)
    staged = {name: [] for name in TARGETS}
    for architecture in ("amd64", "arm64"):
        archive = ROOT / "input" / ("candidate-" + architecture) / "artifacts" / ("images-" + architecture + ".tar.zst")
        with subprocess.Popen(["zstd", "-dc", str(archive)], stdout=subprocess.PIPE) as decompressor:
            subprocess.run(["docker", "load"], stdin=decompressor.stdout, check=True)
            decompressor.stdout.close()
            assert decompressor.wait() == 0
        verified_ids = {item["id"] for item in report["architectures"][architecture]["images"]}
        for component, stable in TARGETS.items():
            local = {"community-server": "morrowsql", "community-router": "morrowsql-router",
                     "community-operator": "morrowsql-operator", "morrowsql": "morrowsql"}[component] + ":" + VERSION
            image = json.loads(run("docker", "image", "inspect", local))[0]
            assert image["Architecture"] == architecture and image["Id"] in verified_ids
            assert image["Config"]["Labels"]["org.opencontainers.image.revision"] == report["revision"]
            candidate = stable + f"-candidate-{run_id}-{architecture}"
            run("docker", "tag", image["Id"], candidate)
            subprocess.run(["docker", "push", "--platform", "linux/" + architecture, candidate], check=True)
            staged[component].append(candidate.split(":")[0] + "@" + manifest(candidate)["digest"])
    # Candidate uploads create repositories first. A missing stable manifest
    # must then be explicit; authentication and network errors are fatal.
    for reference in TARGETS.values():
        result = subprocess.run(["docker", "buildx", "imagetools", "inspect", reference], text=True, capture_output=True)
        if result.returncode == 0:
            raise SystemExit(f"Refusing to replace existing release image: {reference}")
        if not any(reason in result.stderr.lower() for reason in ("manifest unknown", "not found")):
            raise SystemExit(result.stderr)
    published = {}
    for component, reference in TARGETS.items():
        subprocess.run(["docker", "buildx", "imagetools", "create", "--tag", reference, *staged[component]], check=True)
        result = manifest(reference)
        assert {item["platform"]["architecture"] for item in result["manifests"]} == {"amd64", "arm64"}
        published[reference] = result
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
                stream.write(f"{component.replace('-', '_')}={result['digest']}\n")
    (output / "images.json").write_text(json.dumps(published, indent=2) + "\n")
    with (output / "images.json").open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    with (output / "SHA256SUMS").open("a") as stream:
        stream.write(f"{checksum}  images.json\n")


if __name__ == "__main__":
    main()
