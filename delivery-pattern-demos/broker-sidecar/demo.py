#!/usr/bin/env python3
"""demo.py — orchestrates the broker-sidecar demo end-to-end.

Proves:
  1. Broker fetches and renders secret from OpenBao KV v2
  2. Legacy reader reads the rendered file
  3. Rotation detected and re-rendered (new version written to KV)
  4. Reader sees the new value

Needs Docker (real OpenBao dev-mode). Exits 0 on success, non-zero on failure.

Bootstrap secret: the OpenBao token is an OBVIOUS dev value, out of scope.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.chdir(HERE)

BAO_ADDR = "http://127.0.0.1:58201"
BAO_TOKEN = "dev-only-root-token"  # BOOTSTRAP SECRET (obvious dev value)
KV_MOUNT = "secret"
KV_PATH = "apps/legacy-db"
OUTPUT = HERE / "run" / "db.conf"

# The fake secret used in the demo (per AC: S3cr3t-Pg-Pass)
INITIAL_SECRET = {
    "host": "127.0.0.1",
    "port": "5432",
    "dbname": "appdb",
    "username": "app_pg_user",
    "password": "S3cr3t-Pg-Pass",
}

ROTATED_SECRET = {
    "host": "127.0.0.1",
    "port": "5432",
    "dbname": "appdb",
    "username": "app_pg_user",
    "password": "R0tated-Pg-Pass-v2",
}


def bao_request(method: str, path: str, data: dict = None) -> dict:
    """Make an HTTP request to the OpenBao API."""
    url = f"{BAO_ADDR}/v1/{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method,
                                headers={"X-Vault-Token": BAO_TOKEN,
                                         "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body_text = e.read().decode() if e.fp else ""
        raise RuntimeError(f"OpenBao API error {e.code} on {method} {path}: {body_text}") from e


def wait_for_openbao(timeout=30):
    """Wait for OpenBao to become ready."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            url = f"{BAO_ADDR}/v1/sys/health"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=2):
                return
        except Exception:
            time.sleep(1)
    raise RuntimeError(f"OpenBao not ready after {timeout}s")


def seed_secret(secret_data: dict):
    """Write a secret to KV v2."""
    bao_request("POST", f"{KV_MOUNT}/data/{KV_PATH}", {"data": secret_data})


def run_broker():
    """Run the broker in one-shot mode."""
    env = {**os.environ,
           "BROKER_BAO_ADDR": BAO_ADDR,
           "BROKER_BAO_TOKEN": BAO_TOKEN,
           "BROKER_KV_MOUNT": KV_MOUNT,
           "BROKER_KV_PATH": KV_PATH}
    r = subprocess.run([sys.executable, str(HERE / "broker.py")],
                       env=env, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"broker failed: {r.stderr}", file=sys.stderr)
        return False
    print(r.stdout, end="")
    return True


def run_reader() -> str:
    """Run the legacy reader and return its output."""
    r = subprocess.run([sys.executable, str(HERE / "legacy_reader.py")],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"reader failed: {r.stderr}", file=sys.stderr)
        return ""
    return r.stdout


def main():
    print("== broker-sidecar demo ==")
    print()

    # Step 0: bring up OpenBao
    print("→ bringing up OpenBao (dev mode) ...")
    subprocess.run(["docker", "compose", "down", "-v"],
                   cwd=HERE, capture_output=True)
    r = subprocess.run(["docker", "compose", "up", "-d"],
                       cwd=HERE, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"FAIL: docker compose up failed: {r.stderr}", file=sys.stderr)
        sys.exit(1)

    try:
        wait_for_openbao()
        print("  OpenBao ready")
        print()

        # Step 1: seed the initial secret
        print("→ seeding initial secret (password: S3cr3t-Pg-Pass) ...")
        seed_secret(INITIAL_SECRET)
        print("  secret written to KV v2")
        print()

        # Step 2: broker fetches and renders
        print("→ broker: fetch + render ...")
        if not run_broker():
            sys.exit(1)
        print()

        # Step 3: reader reads the rendered file
        print("→ legacy reader reads the rendered config ...")
        output = run_reader()
        if not output:
            sys.exit(1)
        print(output, end="")
        if "S3cr3t-Pg-Pass" not in output:
            print("FAIL: reader did not see the expected password", file=sys.stderr)
            sys.exit(1)
        print("  ✓ reader sees S3cr3t-Pg-Pass")
        print()

        # Step 4: rotate (write new version)
        print("→ rotating secret (writing v2: R0tated-Pg-Pass-v2) ...")
        seed_secret(ROTATED_SECRET)
        print("  new version written")
        print()

        # Step 5: broker detects rotation and re-renders
        print("→ broker: fetch + render (rotation) ...")
        if not run_broker():
            sys.exit(1)
        print()

        # Step 6: reader sees the new value
        print("→ legacy reader reads the re-rendered config ...")
        output = run_reader()
        if not output:
            sys.exit(1)
        print(output, end="")
        if "R0tated-Pg-Pass-v2" not in output:
            print("FAIL: reader did not see the rotated password", file=sys.stderr)
            sys.exit(1)
        print("  ✓ reader sees R0tated-Pg-Pass-v2")
        print()

        print("✅ demo complete — broker fetched, rendered, rotated, and the reader saw both values.")

    finally:
        # Tear down
        subprocess.run(["docker", "compose", "down", "-v"],
                       cwd=HERE, capture_output=True)


if __name__ == "__main__":
    main()
