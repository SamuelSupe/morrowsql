#!/usr/bin/env python3
"""Create private bootstrap input without passing credentials as arguments."""
import os
import pathlib
import re
import sys

directory = pathlib.Path(sys.argv[1])
password = os.environ["MYSQL_ROOT_PASSWORD"]


def literal(value):
    if "\0" in value:
        raise SystemExit("NUL is not allowed in an initialization value")
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


statements = ["SET SESSION sql_mode='';", "SET SESSION sql_log_bin=0;"]
database = os.environ.get("MYSQL_DATABASE", "")
if database:
    if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", database):
        raise SystemExit("MYSQL_DATABASE must contain 1-64 ASCII letters, digits or underscores")
    statements.append(f"CREATE DATABASE `{database}`;")
user = os.environ.get("MYSQL_USER", "")
if user:
    statements.append(f"CREATE USER {literal(user)}@'%' IDENTIFIED BY {literal(os.environ['MYSQL_PASSWORD'])};")
    grant_database = database.replace("_", r"\_")
    statements.append(f"GRANT ALL ON `{grant_database}`.* TO {literal(user)}@'%';")
statements.append(f"ALTER USER 'root'@'localhost' IDENTIFIED BY {literal(password)};")
(directory / "bootstrap.sql").write_text("\n".join(statements) + "\n")
option_password = password.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
(directory / "client.cnf").write_text(f'[client]\nuser=root\npassword="{option_password}"\n')
