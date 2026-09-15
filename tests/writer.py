"""Run inside the client pod; record only server-confirmed commits."""
import json
import os
import pathlib
import time
import uuid

import mysqlsh

session = None
log = pathlib.Path("/work/acknowledged.jsonl")
with log.open("a", buffering=1) as output:
    while not pathlib.Path("/work/stop").exists():
        try:
            if session is None:
                session = mysqlsh.mysql.get_session({
                    "host": "morrow", "port": 6446, "user": "root",
                    "password": os.environ["DATABASE_PASSWORD"],
                    "ssl-mode": "REQUIRED", "connect-timeout": 5000,
                    "net-read-timeout": 5000, "net-write-timeout": 5000,
                })
                session.run_sql("SET SESSION max_execution_time=5000")
            identifier = str(uuid.uuid4())
            session.run_sql("START TRANSACTION")
            session.run_sql("INSERT INTO acceptance.commits VALUES (?, ?)", [identifier, identifier])
            session.run_sql("COMMIT")
            output.write(json.dumps({"id": identifier, "time": time.time()}) + "\n")
            os.fsync(output.fileno())
        except Exception:
            if session:
                try:
                    session.close()
                except Exception:
                    pass
            session = None
        time.sleep(0.2)
if session:
    session.close()
pathlib.Path("/work/stopped").touch()
