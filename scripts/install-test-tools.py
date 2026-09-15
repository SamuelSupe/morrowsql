#!/usr/bin/env python3
"""Install checksum-pinned kind, kubectl and Helm into an isolated directory."""
import hashlib
import io
import json
import os
import pathlib
import platform
import ssl
import tarfile
import urllib.request

root = pathlib.Path(__file__).resolve().parent.parent
lock = json.loads((root / "tests/tools.json").read_text())
system = platform.system().lower()
architecture = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "amd64"}[platform.machine()]
destination = root / ".cache/bin"
destination.mkdir(parents=True, exist_ok=True)
ca = os.environ.get("BUILD_CA_FILE")
if not ca and (root / ".cache/build-ca.pem").exists():
    ca = str(root / ".cache/build-ca.pem")
context = ssl.create_default_context(cafile=ca)
for tool in ("kind", "kubectl", "helm"):
    source = lock[f"{tool}-{system}-{architecture}"]
    with urllib.request.urlopen(source["url"], context=context, timeout=60) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != source["sha256"]:
        raise SystemExit(f"Checksum mismatch for {tool}")
    if "member" in source:
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            data = archive.extractfile(source["member"]).read()
    path = destination / tool
    path.write_bytes(data)
    path.chmod(0o755)
    print(path)
