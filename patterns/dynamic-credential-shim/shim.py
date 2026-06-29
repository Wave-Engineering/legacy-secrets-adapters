#!/usr/bin/env python3
"""shim.py — the credential shim.

Fetches the OpenBao-managed credential for the static role and writes it to the file the
UNCHANGED legacy reader reads. Run it again after a rotation and it rewrites the file with the
new password. The reader never knows the password came from OpenBao or that it rotates.

(In production the shim would be a sidecar/agent re-rendering on lease change, and the file would
be a Cone-of-Silence tmpfs path — see ../cone-of-silence. Here it's a plain file for clarity.)

Bootstrap secret: the OpenBao token below is an OBVIOUS dev value and is out of scope — see
README "Bootstrap secret — out of scope".
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HERE   = Path(__file__).resolve().parent
CONFIG = HERE / "run" / "secrets.json"      # the file the legacy reader reads (gitignored)
ROLE   = "app-static"
# Pinned to the local demo container. NEVER inherit an ambient BAO_ADDR/BAO_TOKEN — they may
# point at a real server. Hard safety guard.
BAO_ENV = {**os.environ,
           "BAO_ADDR":  "http://127.0.0.1:58200",
           "BAO_TOKEN": "dev-only-root-token"}  # BOOTSTRAP SECRET (obvious dev value)

PG_HOST, PG_PORT, PG_DB = "127.0.0.1", "55432", "appdb"


def fetch():
    out = subprocess.run(
        ["bao", "read", "-format=json", f"database/static-creds/{ROLE}"],
        env=BAO_ENV, capture_output=True, text=True, check=True,
    ).stdout
    d = json.loads(out)["data"]
    return d["username"], d["password"]


def materialize():
    user, password = fetch()
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    cfg = {"username": user, "password": password, "host": PG_HOST, "port": PG_PORT, "dbname": PG_DB}
    fd = os.open(CONFIG, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.write(fd, (json.dumps(cfg, indent=2) + "\n").encode())
    os.close(fd)
    print(f"→ shim: wrote OpenBao-managed credential for '{user}' to run/{CONFIG.name}")


if __name__ == "__main__":
    materialize()
