#!/usr/bin/env python3
"""Acceptance tests on three worker containers, never on the user's cluster."""
import json
import secrets
import subprocess
import time

from cluster import Cluster, IMAGES, ROOT, wait


class Acceptance:
    def __init__(self, cluster):
        self.cluster = cluster
        self.password = secrets.token_urlsafe(40)
        cluster.secrets.append(self.password)
        self.results = []

    def record(self, scenario, **values):
        result = {"scenario": scenario, "status": "passed", **values}
        self.results.append(result)
        print(json.dumps(result), flush=True)

    def prepare(self):
        c = self.cluster
        c.apply({"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "morrowsql-credentials"},
                 "stringData": {"rootUser": "root", "rootHost": "%", "rootPassword": self.password}})
        c.install_operator()
        c.install_database()
        members = c.members()
        assert len({p["spec"]["nodeName"] for p in members}) == 3
        assert len(c.get("pvc")["items"]) == 3
        c.primary()
        pdb = c.get("pdb")["items"]
        assert len(pdb) == 1 and pdb[0]["status"]["desiredHealthy"] == 2
        assert c.get("service", "morrow")["spec"]["type"] == "ClusterIP"
        self.record("fresh Helm deployment, three worker nodes, PVCs, single primary, PDB and ClusterIP")

        c.local_sql(c.primary()["metadata"]["name"],
                    "CREATE DATABASE acceptance; CREATE TABLE acceptance.commits("
                    "id CHAR(36) PRIMARY KEY, payload CHAR(36) NOT NULL) ENGINE=InnoDB;")
        c.apply({"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "acceptance-writer"},
                 "data": {"writer.py": (ROOT / "tests/writer.py").read_text()}})
        c.apply({"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "acceptance-client"},
                 "spec": {
                     "nodeSelector": {"node-role.kubernetes.io/control-plane": ""},
                     "tolerations": [{"key": "node-role.kubernetes.io/control-plane", "effect": "NoSchedule"}],
                     "securityContext": {"runAsUser": 27, "runAsGroup": 27, "fsGroup": 27},
                     "containers": [{"name": "client", "image": IMAGES["morrowsql-operator:8.4.11-1"],
                                     "command": ["sleep", "infinity"],
                                     "env": [{"name": "DATABASE_PASSWORD", "valueFrom": {"secretKeyRef": {
                                         "name": "morrowsql-credentials", "key": "rootPassword"}}},
                                             {"name": "MYSQLSH_USER_CONFIG_HOME", "value": "/work"}],
                                     "volumeMounts": [{"name": "work", "mountPath": "/work"},
                                                      {"name": "script", "mountPath": "/script"}]}],
                     "volumes": [{"name": "work", "emptyDir": {}},
                                 {"name": "script", "configMap": {"name": "acceptance-writer"}}]}})
        c.kubectl("wait", "pod/acceptance-client", "--for=condition=Ready", "--timeout=180s")
        routers = [pod for pod in c.get("pods")["items"]
                   if pod["metadata"].get("labels", {}).get("component") == "mysqlrouter"]
        assert len(routers) == 2
        for pod in routers:
            assert self.query("SELECT @@super_read_only", host=pod["status"]["podIP"]) == [[0]]
            assert self.query("SELECT @@super_read_only", host=pod["status"]["podIP"], port=6447) == [[1]]
        self.record("both Routers provide TLS write and read-only connections")
        c.kubectl("exec", "acceptance-client", "--", "bash", "-c",
                  "mysqlsh --py --file /script/writer.py </dev/null >/work/writer.log 2>&1 &")
        wait("first confirmed transactions", lambda: len(self.acknowledged()) >= 5, 60)

    def query(self, sql, host="morrow", port=6446):
        connection = {"host": host, "port": port, "user": "root", "ssl-mode": "REQUIRED",
                      "connect-timeout": 5000, "net-read-timeout": 5000}
        program = ("import mysqlsh,os,json; o=" + repr(connection) +
                   "; o['password']=os.environ['DATABASE_PASSWORD']; s=mysqlsh.mysql.get_session(o); "
                   "print(json.dumps([list(r) for r in s.run_sql(" + repr(sql) + ").fetch_all()])); s.close()")
        result = self.cluster.kubectl("exec", "acceptance-client", "--", "mysqlsh", "--py", "-e", program)
        return json.loads(result.stdout.strip().splitlines()[-1])

    def acknowledged(self):
        result = self.cluster.kubectl("exec", "acceptance-client", "--", "cat", "/work/acknowledged.jsonl", check=False)
        return [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]

    def recovered(self, scenario, started, enforce_target=True):
        observed = time.time()
        wait(scenario + ": writing resumes", lambda: sum(r["time"] > observed for r in self.acknowledged()) >= 5, 120)
        elapsed = time.time() - started
        if enforce_target:
            assert elapsed <= 120, f"{scenario}: {elapsed:.1f}s exceeds the CI target"
        self.record(scenario, recovery_seconds=round(elapsed, 2))

    def simple_faults(self):
        c = self.cluster
        primary_pod = c.primary()
        primary = primary_pod["metadata"]["name"]
        node = primary_pod["spec"]["nodeName"]
        container = self.container_id(node, primary)
        info = json.loads(c.run("docker", "exec", node, "crictl", "inspect", container).stdout)
        started = time.time()
        c.run("docker", "exec", node, "kill", "-KILL", str(info["info"]["pid"]))
        self.recovered("primary process crash", started)
        c.online()
        primary = c.primary()["metadata"]["name"]
        started = time.time()
        c.kubectl("delete", "pod", primary, "--grace-period=1", "--wait=true", "--timeout=60s")
        self.recovered("primary Pod deletion and persistent restart", started)
        c.online()
        node = c.primary()["spec"]["nodeName"]
        started = time.time()
        c.run("docker", "pause", node)
        try:
            self.recovered("primary worker stops responding", started)
        finally:
            c.run("docker", "unpause", node)
        c.online()

    def container_id(self, node, pod_name):
        c = self.cluster
        containers = json.loads(c.run("docker", "exec", node, "crictl", "ps", "-o", "json").stdout)["containers"]
        return next(item["id"] for item in containers
                    if item.get("labels", {}).get("io.kubernetes.pod.name") == pod_name
                    and item["metadata"]["name"] == "mysql")

    def node_sql(self, node, pod_name, sql, timeout=15):
        return self.cluster.run("docker", "exec", node, "crictl", "exec", self.container_id(node, pod_name),
                     "mysql", "-ulocalroot", "-N", "-B", "-e", sql, check=False, timeout=timeout)

    def partition(self):
        c = self.cluster
        primary = c.primary()
        node, pod = primary["spec"]["nodeName"], primary["metadata"]["name"]
        address = json.loads(c.run("docker", "inspect", node).stdout)[0]["NetworkSettings"]["Networks"]["kind"]["IPAddress"]
        started = time.time()
        c.run("docker", "network", "disconnect", "kind", node)
        try:
            self.recovered("majority serves after primary network partition", started)
            try:
                rejected = self.node_sql(node, pod, "INSERT INTO acceptance.commits VALUES(UUID(), 'minority');")
                assert rejected.returncode != 0, "Isolated minority accepted a write"
            except subprocess.TimeoutExpired:
                pass  # Waiting for quorum cannot acknowledge a commit.
            self.record("isolated minority cannot confirm a write")
        finally:
            c.run("docker", "network", "connect", "--ip", address, "kind", node)
        c.online()
        c.primary()

        # Stop two workers together, preserving the control plane and client.
        nodes = [p["spec"]["nodeName"] for p in c.members()][:2]
        paused = []
        try:
            for node in nodes:
                c.run("docker", "pause", node)
                paused.append(node)
            time.sleep(20)
            before = len(self.acknowledged())
            time.sleep(15)
            assert len(self.acknowledged()) == before, "Writes continued without a majority"
            self.record("loss of majority stops confirmed writes without forced quorum")
        finally:
            started = time.time()
            for node in reversed(paused):
                c.run("docker", "unpause", node)
        c.online()
        self.recovered("majority recovery", started, enforce_target=False)

    def maintenance(self):
        c = self.cluster
        for namespace, deployment in (("default", "morrow-router"), ("morrowsql-system", "mysql-operator")):
            started = time.time()
            c.kubectl("rollout", "restart", "deployment/" + deployment, "-n", namespace)
            c.kubectl("rollout", "status", "deployment/" + deployment, "-n", namespace, "--timeout=300s")
            c.online()
            self.recovered(deployment + " restart", started, enforce_target=False)
        node = c.primary()["spec"]["nodeName"]
        started = time.time()
        try:
            c.kubectl("drain", node, "--ignore-daemonsets", "--delete-emptydir-data", "--timeout=180s")
            self.recovered("planned worker maintenance", started)
        finally:
            c.kubectl("uncordon", node)
        c.online()

    def verify_ledger(self, host="morrow"):
        rows = self.query("SELECT id,payload FROM acceptance.commits", host=host)
        actual = {row[0]: row[1] for row in rows}
        confirmed = {row["id"] for row in self.acknowledged()}
        assert confirmed, "No committed workload was observed"
        assert confirmed <= actual.keys(), f"Lost {len(confirmed - actual.keys())} acknowledged transactions"
        assert all(actual[key] == key for key in confirmed)
        self.record("all acknowledged transactions present", target=host, count=len(confirmed))

    def stop_writer(self):
        self.cluster.kubectl("exec", "acceptance-client", "--", "touch", "/work/stop")
        wait("writer stops", lambda: self.cluster.kubectl("exec", "acceptance-client", "--", "test", "-f", "/work/stopped", check=False).returncode == 0, 60)
        (self.cluster.evidence / "acknowledged.json").write_text(json.dumps(self.acknowledged()))

    def retain_volumes(self):
        c = self.cluster
        before = {p["metadata"]["uid"] for p in c.get("pvc")["items"]}
        c.run("helm", "uninstall", "morrow")
        wait("cluster Pods removed", lambda: not c.members(), 300)
        after = {p["metadata"]["uid"] for p in c.get("pvc")["items"]}
        assert before <= after, "Helm uninstall deleted a PVC"
        self.record("Helm uninstall retains persistent volume claims", count=len(before))


def main():
    c = Cluster()
    acceptance = Acceptance(c)
    status = "failed"
    try:
        c.create()
        acceptance.prepare()
        acceptance.simple_faults()
        acceptance.partition()
        acceptance.maintenance()
        acceptance.stop_writer()
        acceptance.verify_ledger()
        # S3 backup/restore runs after the workload stops, so its restore can
        # be compared against the complete set of client acknowledgements.
        from s3_backup import verify_backups
        verify_backups(acceptance)
        status = "passed"
    finally:
        try:
            c.collect()
            for path in c.evidence.glob("*.log"):
                path.write_text(path.read_text().replace(acceptance.password, "[REDACTED]"))
            (c.evidence / "results.json").write_text(json.dumps({
                "status": status, "environment": "kind: one control plane and three worker containers",
                "productionSLA": False, "scenarios": acceptance.results,
            }, indent=2) + "\n")
        finally:
            c.close()


if __name__ == "__main__":
    main()
