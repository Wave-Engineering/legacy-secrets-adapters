#!/usr/bin/env python3
"""legacy-reader — the app WE CANNOT CHANGE.

It reads a config file and connects to Postgres with whatever credential it finds. It has no
idea the password is OpenBao-managed or that it rotates — it just opens a file and connects.
That obliviousness is the whole point: the credential lifecycle changes WITHOUT touching the app.

    ./legacy_reader.py                       # reads run/secrets.json
    CONFIG_PATH=/path ./legacy_reader.py     # or wherever it's told
"""
import json
import os
import subprocess
import sys
from pathlib import Path

CONFIG = Path(os.environ.get("CONFIG_PATH", Path(__file__).resolve().parent / "run" / "secrets.json"))


def die(msg: str):
    bar = "!" * 64
    print(f"\n{bar}", file=sys.stderr)
    print(f"[legacy-reader] FATAL: {msg}", file=sys.stderr)
    print("[legacy-reader] No working credential, no service.", file=sys.stderr)
    print(f"{bar}\n", file=sys.stderr)
    sys.exit(2)


if not CONFIG.exists():
    die(f"cannot find my config file: {CONFIG}")
cfg = json.load(open(CONFIG))

dsn = (f"postgresql://{cfg['username']}:{cfg['password']}@{cfg['host']}:{cfg['port']}"
       f"/{cfg['dbname']}?sslmode=disable&gssencmode=disable")
print(f"[legacy-reader] opened {CONFIG.name}; connecting to {cfg['host']}:{cfg['port']}/{cfg['dbname']} as {cfg['username']} ...")

# A real connection — succeeds or fails for real.
r = subprocess.run(["psql", dsn, "-tAc", "select current_user, now()"], capture_output=True, text=True)
if r.returncode != 0:
    die("Postgres rejected the credential:\n           " + r.stderr.strip().splitlines()[-1])
print(f"[legacy-reader] connected OK as {r.stdout.strip()}")
print("[legacy-reader] (password used in memory to connect — never printed, never logged)")
