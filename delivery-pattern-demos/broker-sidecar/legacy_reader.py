#!/usr/bin/env python3
"""legacy_reader.py — the app WE CANNOT CHANGE.

It reads a rendered config file and prints the database credential it finds. It has no idea
a broker sidecar fetches and manages the secret — it just opens a file and reads. That
obliviousness is the whole point: the credential lifecycle changes WITHOUT touching the app.

    ./legacy_reader.py                       # reads run/db.conf
    CONFIG_PATH=/path ./legacy_reader.py     # or wherever it's told
"""
import configparser
import os
import sys
from pathlib import Path

CONFIG = Path(os.environ.get("CONFIG_PATH", Path(__file__).resolve().parent / "run" / "db.conf"))


def die(msg: str):
    bar = "!" * 64
    print(f"\n{bar}", file=sys.stderr)
    print(f"[legacy-reader] FATAL: {msg}", file=sys.stderr)
    print("[legacy-reader] No working credential, no service.", file=sys.stderr)
    print(f"{bar}\n", file=sys.stderr)
    sys.exit(2)


if not CONFIG.exists():
    die(f"cannot find my config file: {CONFIG}")

parser = configparser.ConfigParser()
parser.read(CONFIG)

try:
    host = parser.get("database", "host")
    port = parser.get("database", "port")
    dbname = parser.get("database", "dbname")
    username = parser.get("database", "username")
    password = parser.get("database", "password")
except (configparser.NoSectionError, configparser.NoOptionError) as e:
    die(f"config parse error: {e}")

print(f"[legacy-reader] opened {CONFIG.name}; found credential for {username}@{host}:{port}/{dbname}")
print(f"[legacy-reader] password value: {password}")
print("[legacy-reader] (in production this would be used to connect — never printed)")
