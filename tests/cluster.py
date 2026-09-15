"""Own exactly one disposable kind cluster and keep its evidence on failure."""
import json
import os
import pathlib
import subprocess
import tempfile
import time
import uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPOSITORY = "ghcr.io/samuelsupe/morrowsql/8.4.11-1"
IMAGES = {
    "morrowsql:8.4.11-1": f"{REPOSITORY}/community-server:8.4.11",
    "morrowsql-router:8.4.11-1": f"{REPOSITORY}/community-router:8.4.11",
    "morrowsql-operator:8.4.11-1": f"{REPOSITORY}/community-operator:8.4.9-2.1.11",
}
NODE_IMAGE = "kindest/node:v1.35.8@sha256:07b2536e30b803ed61d1677a79df6115f798ce64c80f9e22f6ed45afd09323c0"


def wait(description, predicate, timeout=600):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(3)
    raise TimeoutError(description)


class Cluster:
    def __init__(self):
        self.name = "morrowsql-" + uuid.uuid4().hex[:10]
        self.evidence = ROOT / "artifacts" / self.name
        self.evidence.mkdir(parents=True)
        self.environment = dict(os.environ, KUBECONFIG=str(self.evidence / "kubeconfig"))
        self.created = False
        self.secrets = []
        self.charts = pathlib.Path(os.environ.get("MORROWSQL_CHART_DIRECTORY", ROOT / "charts"))

    def redact(self, text):
        for value in self.secrets:
            text = text.replace(value, "[REDACTED]")
        return text

    def run(self, *args, input=None, check=True, timeout=600):
        result = subprocess.run(args, input=input, text=True, capture_output=True,
                                env=self.environment, timeout=timeout)
        if check and result.returncode:
            raise RuntimeError(self.redact(f"Command failed: {' '.join(args)}\n{result.stderr[-8000:]}"))
        return result

    def kubectl(self, *args, **kwargs):
        return self.run("kubectl", "--request-timeout=30s", *args, **kwargs)

    def get(self, resource, name=None):
        args = ["get", resource]
        if name:
            args.append(name)
        result = self.kubectl(*args, "-o", "json", check=False)
        return json.loads(result.stdout) if result.returncode == 0 else {}

    def apply(self, resource):
        return self.kubectl("apply", "-f", "-", input=json.dumps(resource))

    def create(self):
        configuration = self.evidence / "kind.json"
        configuration.write_text(json.dumps({
            "kind": "Cluster", "apiVersion": "kind.x-k8s.io/v1alpha4",
            "nodes": [{"role": "control-plane"}] + [{"role": "worker"}] * 3,
        }))
        self.created = True
        result = self.run("kind", "create", "cluster", "--name", self.name,
                         "--image", NODE_IMAGE, "--config", str(configuration),
                         "--kubeconfig", self.environment["KUBECONFIG"], "--wait", "180s", timeout=1800)
        (self.evidence / "kind-create.log").write_text(result.stdout + result.stderr)
        nodes = self.get("nodes")["items"]
        assert len(nodes) == 4
        assert all(n["status"]["nodeInfo"]["kubeletVersion"].startswith("v1.35.") for n in nodes)
        for node in nodes:
            memory = "2g" if node["metadata"]["name"].endswith("control-plane") else "3g"
            self.run("docker", "update", "--memory", memory, "--memory-swap", memory, node["metadata"]["name"])
        for local, target in IMAGES.items():
            self.run("docker", "tag", local, target)
        images = json.loads(self.run("docker", "image", "inspect", *IMAGES.values()).stdout)
        (self.evidence / "images.json").write_text(json.dumps([
            {"id": item["Id"], "architecture": item["Architecture"], "tags": item["RepoTags"]} for item in images], indent=2))
        self.run("kind", "load", "docker-image", "--name", self.name, *IMAGES.values())

    def install_operator(self):
        result = self.run("helm", "install", "morrowsql-operator", str(self.charts / "morrowsql-operator"),
                         "--namespace", "morrowsql-system", "--create-namespace", "--wait", "--timeout", "5m")
        (self.evidence / "operator-install.log").write_text(result.stdout + result.stderr)

    def load_fixture(self, reference):
        tag = reference.split("@")[0]
        self.run("docker", "pull", reference)
        self.run("docker", "tag", reference, tag)
        architecture = self.run("docker", "image", "inspect", tag, "--format", "{{.Architecture}}").stdout.strip()
        # Docker's containerd store can retain a multi-platform index after a
        # native pull. Export only the available platform, so kind does not
        # attempt to import absent manifests for other architectures.
        with tempfile.TemporaryDirectory(prefix="morrowsql-image-") as directory:
            archive = str(pathlib.Path(directory) / "image.tar")
            self.run("docker", "image", "save", "--platform", "linux/" + architecture,
                     "--output", archive, tag)
            self.run("kind", "load", "image-archive", "--name", self.name, archive)
        return tag

    def install_database(self, name="morrow", extra=None):
        args = ["helm", "install", name, str(self.charts / "morrowsql"), "-f", str(ROOT / "tests/ci-values.yaml")]
        if extra:
            path = self.evidence / f"{name}-values.json"
            path.write_text(json.dumps(extra))
            args += ["-f", str(path)]
        self.run(*args)
        self.online(name)

    def online(self, name="morrow"):
        def healthy():
            status = self.get("innodbcluster", name).get("status", {}).get("cluster", {})
            if status.get("status") != "ONLINE" or status.get("onlineInstances") != 3:
                return False
            members = self.members(name)
            if len(members) != 3:
                return False
            for member in members:
                if member["metadata"].get("deletionTimestamp") or member.get("status", {}).get("phase") != "Running":
                    return False
                result = self.local_sql(member["metadata"]["name"],
                    "SELECT COUNT(*) FROM performance_schema.replication_group_members WHERE MEMBER_STATE='ONLINE';", check=False)
                if result.returncode != 0 or result.stdout.strip() != "3":
                    return False
            return True
        wait(f"{name}: three ONLINE members", healthy, 900)
        self.kubectl("rollout", "status", "deployment/" + name + "-router", "--timeout=300s")

    def members(self, name="morrow"):
        return [p for p in self.get("pods").get("items", [])
            if p["metadata"].get("labels", {}).get("mysql.oracle.com/cluster") == name
            and p["metadata"].get("labels", {}).get("component") == "mysqld"]

    def local_sql(self, pod, query, check=True):
        return self.kubectl("exec", pod, "-c", "mysql", "--", "mysql", "-ulocalroot", "-N", "-B", "-e", query, check=check)

    def primary(self):
        primaries = []
        for pod in self.members():
            result = self.local_sql(pod["metadata"]["name"], "SELECT @@super_read_only;", check=False)
            if result.returncode == 0 and result.stdout.strip() == "0":
                primaries.append(pod)
        assert len(primaries) == 1, f"Expected exactly one writable primary; found {len(primaries)}"
        return primaries[0]

    def collect(self):
        if not self.created:
            return
        for resource in ("nodes", "pods", "pvc", "pv", "innodbcluster", "mysqlbackup", "events", "pdb"):
            result = self.kubectl("get", resource, "-A", "-o", "json", check=False)
            (self.evidence / f"{resource}.json").write_text(self.redact(result.stdout + result.stderr))
        for pod in self.get("pods").get("items", []):
            name = pod["metadata"]["name"]
            for container in pod["spec"].get("initContainers", []) + pod["spec"].get("containers", []):
                result = self.kubectl("logs", name, "-c", container["name"], "--tail=2000", check=False)
                (self.evidence / f"{name}-{container['name']}.log").write_text(self.redact(result.stdout + result.stderr))
        result = self.kubectl("logs", "-n", "morrowsql-system", "deployment/mysql-operator", "--tail=3000", check=False)
        (self.evidence / "operator.log").write_text(self.redact(result.stdout + result.stderr))

    def close(self):
        if self.created:
            self.run("kind", "delete", "cluster", "--name", self.name, check=False)
        # A kubeconfig contains an administrator client key; it is never an artifact.
        pathlib.Path(self.environment["KUBECONFIG"]).unlink(missing_ok=True)
