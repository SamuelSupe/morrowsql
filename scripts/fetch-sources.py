#!/usr/bin/env python3
"""Fetch release sources by immutable commit and verify their archive hashes."""
import hashlib
import json
import os
import pathlib
import shutil
import ssl
import tarfile
import tempfile
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fetch(url, archive, expected):
    if not archive.exists():
        partial = archive.with_suffix(".partial")
        print(f"Fetching {archive.name}", flush=True)
        context = ssl.create_default_context(cafile=os.environ.get("BUILD_CA_FILE"))
        with urllib.request.urlopen(url, context=context, timeout=120) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output)
        if digest(partial) != expected:
            raise SystemExit(f"Archive checksum mismatch: {archive.name}")
        partial.replace(archive)
    if digest(archive) != expected:
        raise SystemExit(f"Cached archive checksum mismatch: {archive.name}")


def main():
    release = json.loads((ROOT / "release.json").read_text())
    archives = ROOT / ".cache/archives"
    sources = ROOT / ".cache/src"
    archives.mkdir(parents=True, exist_ok=True)
    sources.mkdir(parents=True, exist_ok=True)
    for name, source in release["sources"].items():
        expected = source["sha256"]
        archive = archives / f'{name}-{source["commit"]}.tar.gz'
        url = f'https://codeload.github.com/{source["repository"]}/tar.gz/{source["commit"]}'
        fetch(url, archive, expected)
        target = sources / name
        marker = target / ".morrowsql-source"
        if marker.exists() and marker.read_text().strip() == source["commit"]:
            continue
        if target.exists():
            raise SystemExit(f"Unverified source directory exists: {target}")
        with tempfile.TemporaryDirectory(dir=sources) as temporary:
            unpacked = pathlib.Path(temporary)
            with tarfile.open(archive) as bundle:
                bundle.extractall(unpacked, filter="data")
            entries = list(unpacked.iterdir())
            if len(entries) != 1 or not entries[0].is_dir():
                raise SystemExit(f"Unexpected source archive layout: {name}")
            shutil.move(str(entries[0]), target)
        marker.write_text(source["commit"] + "\n")
        print(f"Verified {name}: {source['commit']}", flush=True)
    python_sources = ROOT / ".cache/python-sources"
    python_sources.mkdir(exist_ok=True)
    for source in json.loads((ROOT / "python-sources.json").read_text()):
        fetch(source["url"], python_sources / source["filename"], source["sha256"])


if __name__ == "__main__":
    main()
