"""S3 backup status and same-release restore using an isolated MinIO service."""
import secrets

from cluster import wait

MINIO = "quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e"
MC = "quay.io/minio/mc:RELEASE.2025-08-13T08-35-41Z@sha256:a7fe349ef4bd8521fb8497f55c6042871b2ae640607cf99d9bede5e9bdf11727"


def verify_backups(acceptance):
    c = acceptance.cluster
    minio_image = c.load_fixture(MINIO)
    mc_image = c.load_fixture(MC)
    access, secret = secrets.token_hex(12), secrets.token_hex(24)
    c.secrets.append(secret)
    c.apply({"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "minio-credentials"},
             "stringData": {"access": access, "secret": secret,
                            "mc-host": f"http://{access}:{secret}@minio:9000"}})
    c.apply({"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "s3-credentials"},
             "stringData": {"config": "[default]\nregion=us-east-1\n",
                            "credentials": f"[default]\naws_access_key_id={access}\naws_secret_access_key={secret}\n"}})
    c.apply({"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "minio", "labels": {"app": "minio"}},
             "spec": {"nodeSelector": {"node-role.kubernetes.io/control-plane": ""},
                      "tolerations": [{"key": "node-role.kubernetes.io/control-plane", "effect": "NoSchedule"}],
                      "containers": [{"name": "minio", "image": minio_image, "args": ["server", "/data"],
                                      "env": [{"name": name, "valueFrom": {"secretKeyRef": {
                                          "name": "minio-credentials", "key": key}}}
                                              for name, key in (("MINIO_ROOT_USER", "access"), ("MINIO_ROOT_PASSWORD", "secret"))],
                                      "readinessProbe": {"httpGet": {"path": "/minio/health/ready", "port": 9000}},
                                      "volumeMounts": [{"name": "data", "mountPath": "/data"}]}],
                      "volumes": [{"name": "data", "emptyDir": {}}]}})
    c.apply({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "minio"},
             "spec": {"selector": {"app": "minio"}, "ports": [{"port": 9000, "targetPort": 9000}]}})
    c.kubectl("wait", "pod/minio", "--for=condition=Ready", "--timeout=240s")
    c.apply({"apiVersion": "batch/v1", "kind": "Job", "metadata": {"name": "create-backup-bucket"},
             "spec": {"backoffLimit": 2, "template": {"spec": {"restartPolicy": "Never",
                 "containers": [{"name": "mc", "image": mc_image, "args": ["mb", "--ignore-existing", "ci/morrowsql"],
                                 "env": [{"name": "MC_HOST_ci", "valueFrom": {"secretKeyRef": {
                                     "name": "minio-credentials", "key": "mc-host"}}}]}]}}}})
    c.kubectl("wait", "job/create-backup-bucket", "--for=condition=Complete", "--timeout=180s")

    def storage(bucket="morrowsql"):
        return {"s3": {"bucketName": bucket, "config": "s3-credentials", "profile": "default",
                       "prefix": "acceptance", "endpoint": "http://minio:9000"}}

    def backup(name, bucket):
        c.apply({"apiVersion": "mysql.oracle.com/v2", "kind": "MySQLBackup", "metadata": {"name": name},
                 "spec": {"clusterName": "morrow", "deleteBackupData": False,
                          "backupProfile": {"name": name, "dumpInstance": {"dumpOptions": {"threads": 2}, "storage": storage(bucket)}}}})

    backup("expected-failure", "missing-bucket")
    wait("backup failure status is visible",
         lambda: c.get("mysqlbackup", "expected-failure").get("status", {}).get("status") == "Error", 600)
    acceptance.record("S3 backup failure is visible in MySQLBackup status")
    backup("same-release", "morrowsql")
    wait("S3 backup completed",
         lambda: c.get("mysqlbackup", "same-release").get("status", {}).get("status") == "Completed", 600)
    status = c.get("mysqlbackup", "same-release")["status"]
    assert status["method"] == "dump-instance/s3"
    assert status["completionTime"] and status["output"]
    acceptance.record("one-time logical S3 backup completed")

    # Exercise the upstream CronJob controller with a schedule occurring during
    # this test. Disable it after the first completed scheduled backup.
    profile = {"name": "scheduled-s3", "dumpInstance": {"dumpOptions": {"threads": 2}, "storage": storage()}}
    import json
    c.kubectl("patch", "innodbcluster", "morrow", "--type=merge", "-p", json.dumps({"spec": {
        "backupProfiles": [profile], "backupSchedules": [{"name": "acceptance-schedule", "schedule": "* * * * *",
            "backupProfileName": "scheduled-s3", "enabled": True, "deleteBackupData": False}]}}))
    wait("scheduled backup completed", lambda: any(
        item["metadata"]["name"] not in ("expected-failure", "same-release")
        and item.get("status", {}).get("status") == "Completed"
        for item in c.get("mysqlbackup").get("items", [])), 600)
    c.kubectl("patch", "innodbcluster", "morrow", "--type=merge", "-p", json.dumps({"spec": {"backupSchedules": []}}))
    acceptance.record("scheduled logical S3 backup completed")
    # The restore uses independent PVCs; stopping the source also exercises its
    # uninstall contract without doubling database memory on a shared test host.
    acceptance.retain_volumes()
    c.install_database("restored", {"backup": {"bucket": "morrowsql", "existingSecret": "s3-credentials",
                                               "endpoint": "http://minio:9000"},
                                    "restore": {"enabled": True, "prefix": "acceptance/" + status["output"]}})
    acceptance.verify_ledger(host="restored")
    acceptance.record("S3 backup restored to a fresh same-release three-member cluster")
