#!/usr/bin/env python3
"""Prepare public assets only from a successful native verification run."""
import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import tarfile
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPOSITORY = "SamuelSupe/morrowsql"
VERSION = "8.4.11-1"


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_run(run_id):
    if not run_id.isdecimal():
        raise SystemExit("The verification run ID must be numeric")
    run = json.loads(command("gh", "api", f"repos/{REPOSITORY}/actions/runs/{run_id}"))
    revision = command("git", "rev-parse", "HEAD")
    assert run["repository"]["full_name"] == REPOSITORY
    assert run["path"] == ".github/workflows/build.yml"
    assert run["head_sha"] == revision, "The release tree differs from the verified source revision"
    assert run["status"] == "completed" and run["conclusion"] == "success", "Verification did not pass"
    jobs = json.loads(command("gh", "api", f"repos/{REPOSITORY}/actions/runs/{run_id}/jobs?per_page=100"))
    expected = {"source", "build (amd64, ubuntu-24.04)", "build (arm64, ubuntu-24.04-arm)"}
    assert expected <= {job["name"] for job in jobs["jobs"] if job["conclusion"] == "success"}
    return run


def xml_summary(path):
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    assert cases, f"Empty test evidence: {path}"
    assert not list(root.iter("failure")) and not list(root.iter("error")), f"Test failures in {path}"
    assert all(case.get("status") not in ("fail", "failed", "timeout") for case in cases), str(path)
    skipped = sum(case.get("status") in ("skipped", "disabled", "notrun") or case.find("skipped") is not None
                  for case in cases)
    assert len(cases) > skipped, f"No executed tests in {path}"
    return {"cases": len(cases), "passed": len(cases) - skipped, "skipped": skipped}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    run = verify_run(args.run_id)
    if args.check_only:
        print(run["html_url"])
        return
    output = ROOT / "dist/public"
    output.mkdir(parents=True, exist_ok=False)
    inputs = ROOT / "input"
    source = inputs / "corresponding-source" / f"morrowsql-{VERSION}-source.tar.gz"
    source_checksum = source.with_name(source.name + ".sha256").read_text().split()[0]
    assert digest(source) == source_checksum
    shutil.copy2(source, output / source.name)
    report = {"version": VERSION, "revision": run["head_sha"], "verificationRun": run["html_url"],
              "environment": "Native GitHub runners; kind with one control plane and three worker containers",
              "productionSLA": False, "architectures": {}}
    for architecture in ("amd64", "arm64"):
        candidate = inputs / ("candidate-" + architecture)
        evidence = candidate / "artifacts"
        build = json.loads((evidence / "build-info.json").read_text())
        assert build["revision"] == run["head_sha"]
        archive = candidate / "dist" / f"morrowsql-{VERSION}-linux-{architecture}.tar.gz"
        assert digest(archive) == archive.with_name(archive.name + ".sha256").read_text().split()[0]
        shutil.copy2(archive, output / archive.name)
        standalone = [json.loads(p.read_text()) for p in evidence.glob("standalone-*/results.json")]
        assert {r["binaryArchive"] for r in standalone} == {False, True}
        assert all(len(r["passed"]) == 6 and r["imageId"].startswith("sha256:") for r in standalone)
        ha_paths = list(evidence.glob("morrowsql-*/results.json"))
        assert len(ha_paths) == 1, "Expected exactly one complete HA acceptance run"
        ha = json.loads(ha_paths[0].read_text())
        assert ha["status"] == "passed"
        assert all(r["status"] == "passed" for r in ha["scenarios"])
        assert any(r["scenario"] == "S3 backup restored to a fresh same-release three-member cluster" for r in ha["scenarios"])
        images = json.loads((ha_paths[0].parent / "images.json").read_text())
        assert {item["architecture"] for item in images} == {architecture}
        for path in (evidence / "audit").glob("*-vulnerabilities.json"):
            scan = json.loads(path.read_text())
            assert not any(result.get("Vulnerabilities") for result in scan.get("Results", [])), str(path)
        scans = list((evidence / "audit").glob("*-vulnerabilities.json"))
        assert len(scans) == 3, "Missing component vulnerability results"
        sboms = list((evidence / "audit").glob("*.spdx.json"))
        assert len(sboms) == 3
        for sbom in sboms:
            shutil.copy2(sbom, output / sbom.name.replace(".spdx.json", f"-{architecture}.spdx.json"))
        report["architectures"][architecture] = {
            "unit": xml_summary(evidence / "upstream/unit.xml"),
            "mtr": xml_summary(evidence / "upstream/mtr.xml"),
            "standalone": standalone, "ha": ha, "images": images,
        }
        bundle = output / f"morrowsql-{VERSION}-validation-{architecture}.tar.gz"
        with tarfile.open(bundle, "w:gz") as target:
            for path in sorted(evidence.iterdir()):
                if path.name.startswith("images-") or path.name.endswith("build.log"):
                    continue
                target.add(path, arcname=f"validation-{architecture}/{path.name}")
    for chart in ("morrowsql", "morrowsql-operator"):
        command("helm", "package", str(ROOT / "charts" / chart), "--destination", str(output))
    (output / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = [f"# MorrowSQL {VERSION}", "", f"Verified source revision: `{run['head_sha']}`.", "",
        f"Native verification and build logs: [{args.run_id}]({run['html_url']}).", "",
        "Fresh standalone operation, three-member Kubernetes HA, and same-release S3 recovery.", "",
        "| Architecture | Unit passed | MTR passed | MTR skipped/disabled | HA scenarios |",
        "| --- | ---: | ---: | ---: | ---: |"]
    for architecture, result in report["architectures"].items():
        lines.append(f"| {architecture} | {result['unit']['passed']} | {result['mtr']['passed']} | "
                     f"{result['mtr']['skipped']} | {len(result['ha']['scenarios'])} |")
    lines += ["", "HA results come from isolated multi-node CI simulations and are not a production SLA.",
        "Migration, version upgrades, cross-version recovery and a fixed two-hour soak are outside this release.",
        "MTR skip reasons and individual failures/recovery timings are retained in the evidence archives.", "",
        "Anonymous downloads, pulls and fresh installations are checked by the publication workflow after publication.",
        "See that workflow's final public-install jobs for those results.", "",
        "## Verify", "", "```sh", "sha256sum --check SHA256SUMS",
        f"gh attestation verify morrowsql-{VERSION}-source.tar.gz --repo {REPOSITORY}", "```", "",
        "The SPDX files cover runtime packages and source-built components; security review scope is documented in the repository."]
    (output / "validation.md").write_text("\n".join(lines) + "\n")
    (output / "SHA256SUMS").write_text("".join(f"{digest(path)}  {path.name}\n"
        for path in sorted(output.iterdir()) if path.is_file()))
    print(output)


if __name__ == "__main__":
    main()
