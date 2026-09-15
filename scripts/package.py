#!/usr/bin/env python3
"""Package the native installation and the exact inputs used to build it."""
import argparse
import gzip
import hashlib
import json
import os
import pathlib
import subprocess
import tarfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
os.chdir(ROOT)
release = json.loads((ROOT / "release.json").read_text())
version = release["version"]
if (ROOT / "BUILDINFO.json").exists():
    build_info = json.loads((ROOT / "BUILDINFO.json").read_text())
else:
    build_info = {
        "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "sourceDateEpoch": int(subprocess.check_output(["git", "show", "-s", "--format=%ct", "HEAD"])),
    }
epoch = build_info["sourceDateEpoch"]


def archive(path, entries):
    if path.exists():
        raise SystemExit(f"Refusing to replace existing artifact: {path}")
    temporary = path.with_suffix(path.suffix + ".partial")

    def normalize(info):
        if "mysql-test" in pathlib.PurePosixPath(info.name).parts:
            return None
        info.uid = info.gid = 0
        info.uname = info.gname = "root"
        info.mtime = epoch
        return info

    try:
        with temporary.open("wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=epoch) as compressed:
            with tarfile.open(fileobj=compressed, mode="w|") as output:
                for source, destination in entries:
                    output.add(source, arcname=destination, filter=normalize)
        temporary.rename(path)
    finally:
        temporary.unlink(missing_ok=True)
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    path.with_name(path.name + ".sha256").write_text(f"{digest}  {path.name}\n")
    print(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("component", choices=["binary", "source"])
    parser.add_argument("--arch", choices=["amd64", "arm64"])
    args = parser.parse_args()
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    prefix = f"morrowsql-{version}"
    if args.component == "binary":
        if not args.arch:
            parser.error("binary packaging requires --arch")
        stage = ROOT / "build/stage/opt/morrowsql"
        server = stage / "bin/mysqld"
        if not server.exists():
            server = stage / "sbin/mysqld"
        description = subprocess.check_output(["file", str(server)], text=True)
        expected = {"arm64": "ARM aarch64", "amd64": "x86-64"}[args.arch]
        if expected not in description:
            raise SystemExit(f"Native architecture mismatch: {description}")
        directory = f"{prefix}-linux-{args.arch}"
        entries = [(stage, directory), (ROOT / "docs/binary.md", f"{directory}/INSTALL.md"),
                   (ROOT / "docs/binary.zh-CN.md", f"{directory}/INSTALL.zh-CN.md"),
                   (ROOT / "packaging/my.cnf", f"{directory}/my.cnf.example"),
                   (ROOT / "release.json", f"{directory}/release.json"),
                   (ROOT / "licenses", f"{directory}/licenses"),
                   (ROOT / "build/build-packages.tsv", f"{directory}/build-packages.tsv")]
        archive(output / f"{directory}.tar.gz", entries)
    else:
        if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
            raise SystemExit("Commit the complete source tree before creating a source artifact")
        # git ls-files includes newly staged distribution scripts and never
        # includes local credentials, logs, generated objects or build caches.
        tracked = subprocess.check_output(["git", "ls-files", "-z"]).decode().split("\0")
        entries = [(ROOT / name, f"{prefix}-source/{name}") for name in tracked if name]
        metadata = ROOT / ".cache/BUILDINFO.json"
        metadata.write_text(json.dumps(build_info, indent=2) + "\n")
        entries.append((metadata, f"{prefix}-source/BUILDINFO.json"))
        for name, source in release["sources"].items():
            filename = f"{name}-{source['commit']}.tar.gz"
            path = ROOT / ".cache/archives" / filename
            with path.open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if actual != source["sha256"]:
                raise SystemExit(f"Unverified source: {filename}")
            entries.append((path, f"{prefix}-source/.cache/archives/{filename}"))
        for source in json.loads((ROOT / "python-sources.json").read_text()):
            path = ROOT / ".cache/python-sources" / source["filename"]
            with path.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != source["sha256"]:
                    raise SystemExit(f"Unverified Python source: {path.name}")
            entries.append((path, f"{prefix}-source/.cache/python-sources/{path.name}"))
        archive(output / f"{prefix}-source.tar.gz", entries)


if __name__ == "__main__":
    main()
