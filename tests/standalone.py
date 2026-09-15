#!/usr/bin/env python3
"""Exercise fresh deployment, credentials, durability and same-release restore."""
import json
import os
import pathlib
import secrets
import subprocess
import tempfile
import time
import uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
IMAGE = os.environ.get("MORROWSQL_IMAGE", "morrowsql:8.4.11-1")


def docker(*arguments, input=None, check=True):
    return subprocess.run(["docker", *arguments], input=input, text=True,
                          capture_output=True, check=check)


def client_file(path, user, password):
    quoted = password.replace("\\", "\\\\").replace('"', '\\"')
    path.write_text(f'[client]\nuser={user}\npassword="{quoted}"\n')
    path.chmod(0o600)


def main():
    image_id = docker("image", "inspect", IMAGE, "--format", "{{.Id}}").stdout.strip()
    suffix = uuid.uuid4().hex[:10]
    names = [f"morrowsql-{suffix}-{role}" for role in ("source", "restore", "reject")]
    volumes = [name + "-data" for name in names]
    evidence = ROOT / "artifacts" / f"standalone-{suffix}"
    evidence.mkdir(parents=True)
    results = []
    created_containers, created_volumes = [], []
    root_password = secrets.token_urlsafe(32) + "'\\\""
    app_password = secrets.token_urlsafe(32)

    def sql(name, statement, user="root", tcp=False, check=True):
        arguments = ["exec", "-i", name, "mysql", f"--defaults-extra-file=/run/secrets/{user}.cnf", "-N", "-B"]
        if tcp:
            arguments += ["--host=127.0.0.1", "--protocol=tcp", "--ssl-mode=REQUIRED"]
        return docker(*arguments, input=statement, check=check)

    def ready(name):
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            if sql(name, "SELECT 1;", check=False).returncode == 0:
                return
            running = docker("inspect", "-f", "{{.State.Running}}", name, check=False)
            if running.stdout.strip() == "false":
                raise RuntimeError(f"{name} exited during startup")
            time.sleep(2)
        raise RuntimeError(f"{name} did not become ready")

    with tempfile.TemporaryDirectory(prefix="morrowsql-secrets-") as private:
        private = pathlib.Path(private) / "mounted"
        private.mkdir(mode=0o755)
        (private / "root-password").write_text(root_password)
        (private / "app-password").write_text(app_password)
        client_file(private / "root.cnf", "root", root_password)
        client_file(private / "app.cnf", "app", app_password)
        client_file(private / "wrong.cnf", "app", secrets.token_urlsafe(32))
        # The runtime mysql UID needs to read mounted files; the host directory
        # stays private and is removed when this test finishes.
        for path in private.iterdir():
            path.chmod(0o644)

        def start(name, volume):
            docker("volume", "create", "--label", "morrowsql.test=" + suffix, volume)
            created_volumes.append(volume)
            binary = os.environ.get("MORROWSQL_BINARY_DIRECTORY")
            mounts = ["-v", f"{pathlib.Path(binary).resolve()}:/opt/morrowsql:ro"] if binary else []
            docker("run", "-d", "--name", name, "--label", "morrowsql.test=" + suffix,
                   "--memory=1536m", "-v", f"{volume}:/var/lib/mysql",
                   "-v", f"{private}:/run/secrets:ro",
                   "-v", f"{ROOT / 'build/test-client'}:/test-client:ro",
                   "-e", "MYSQL_ROOT_PASSWORD_FILE=/run/secrets/root-password",
                   "-e", "MYSQL_PASSWORD_FILE=/run/secrets/app-password",
                   "-e", "MYSQL_DATABASE=app_db", "-e", "MYSQL_USER=app", *mounts, image_id)
            created_containers.append(name)
            ready(name)

        try:
            source, restore, rejected = names
            start(source, volumes[0])
            comment = sql(source, "SELECT @@version_comment;").stdout.strip()
            assert comment == "MorrowSQL 8.4.11-1", comment
            uid = docker("exec", source, "cat", "/proc/1/status").stdout
            assert "Uid:\t27\t27\t27\t27" in uid
            results.append("fresh initialization and non-root server")

            sql(source, "CREATE TABLE app_db.entries(id BIGINT PRIMARY KEY, value VARCHAR(100));")
            output = sql(source, "START TRANSACTION; INSERT INTO app_db.entries VALUES(1,'committed'); COMMIT; "
                         "START TRANSACTION; INSERT INTO app_db.entries VALUES(2,'rolled back'); ROLLBACK; "
                         "SELECT COUNT(*) FROM app_db.entries;", user="app", tcp=True).stdout.strip()
            assert output == "1", output
            docker("exec", source, "/test-client")
            denied = sql(source, "SELECT 1;", user="wrong", tcp=True, check=False)
            assert denied.returncode != 0
            cleartext = docker("exec", source, "mysql", "--defaults-extra-file=/run/secrets/app.cnf",
                               "--host=127.0.0.1", "--protocol=tcp", "--ssl-mode=DISABLED", "-e", "SELECT 1", check=False)
            assert cleartext.returncode != 0
            sql(source, "CREATE DATABASE appXdb;")
            denied = sql(source, "SHOW TABLES FROM appXdb;", user="app", tcp=True, check=False)
            assert denied.returncode != 0
            results.append("TLS, authentication, grant boundary, prepared statements, commit and rollback")

            docker("restart", source)
            ready(source)
            assert sql(source, "SELECT COUNT(*) FROM app_db.entries;").stdout.strip() == "1"
            sql(source, "INSERT INTO app_db.entries VALUES(3,'acknowledged before crash');")
            docker("kill", "--signal=KILL", source)
            docker("start", source)
            ready(source)
            assert sql(source, "SELECT GROUP_CONCAT(id ORDER BY id) FROM app_db.entries;").stdout.strip() == "1,3"
            results.append("persistent restart and acknowledged-transaction crash recovery")

            dump = docker("exec", source, "mysqldump", "--defaults-extra-file=/run/secrets/root.cnf",
                          "--single-transaction", "--set-gtid-purged=OFF", "--databases", "app_db").stdout
            start(restore, volumes[1])
            sql(restore, dump)
            assert sql(restore, "SELECT GROUP_CONCAT(id ORDER BY id) FROM app_db.entries;").stdout.strip() == "1,3"
            results.append("same-release backup and fresh restore")

            outcome = docker("run", "--name", rejected, "-v", f"{private}:/run/secrets:ro",
                             "-e", "MYSQL_ROOT_PASSWORD=conflicting-input",
                             "-e", "MYSQL_ROOT_PASSWORD_FILE=/run/secrets/root-password", image_id, check=False)
            created_containers.append(rejected)
            assert outcome.returncode != 0
            assert "set either MYSQL_ROOT_PASSWORD" in outcome.stderr
            results.append("ambiguous credential inputs rejected")

            docker("rm", rejected)
            created_containers.remove(rejected)
            docker("volume", "create", volumes[2])
            created_volumes.append(volumes[2])
            docker("run", "--rm", "-v", f"{volumes[2]}:/var/lib/mysql",
                   "--entrypoint", "sh", image_id, "-c", "touch /var/lib/mysql/incomplete")
            outcome = docker("run", "--name", rejected, "-v", f"{volumes[2]}:/var/lib/mysql",
                             "-v", f"{private}:/run/secrets:ro",
                             "-e", "MYSQL_ROOT_PASSWORD_FILE=/run/secrets/root-password", image_id, check=False)
            created_containers.append(rejected)
            assert outcome.returncode != 0
            assert "data directory is not empty" in outcome.stderr
            results.append("incomplete initialization rejected without overwriting data")
        finally:
            leaked = False
            for name in created_containers:
                logs = docker("logs", name, check=False)
                text = logs.stdout + logs.stderr
                if root_password in text or app_password in text:
                    leaked = True
                    text = text.replace(root_password, "[REDACTED]").replace(app_password, "[REDACTED]")
                (evidence / f"{name}.log").write_text(text)
            for name in reversed(created_containers):
                docker("rm", "-f", name, check=False)
            for volume in reversed(created_volumes):
                docker("volume", "rm", volume, check=False)
            if leaked:
                raise RuntimeError("credentials appeared in container logs")
    (evidence / "results.json").write_text(json.dumps({"image": IMAGE, "imageId": image_id,
        "binaryArchive": bool(os.environ.get("MORROWSQL_BINARY_DIRECTORY")), "passed": results}, indent=2) + "\n")
    print(json.dumps({"status": "passed", "scenarios": results, "evidence": str(evidence)}))


if __name__ == "__main__":
    main()
