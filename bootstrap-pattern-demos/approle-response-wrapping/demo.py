#!/usr/bin/env python3
"""demo.py — orchestrates the approle-response-wrapping bootstrap demo end-to-end.

Proves:
  1. Deployer wraps a SecretID via Ansible playbook
  2. Materializer unwraps and authenticates via AppRole
  3. Replay of the same wrapping token fails (single-use)
  4. Expired wrapping token fails (TTL)

Requires: Docker + OpenBao + Ansible + Python + hvac-free (uses urllib only).
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN_DIR = HERE / "run"
BAO_ADDR = "http://127.0.0.1:58201"
BAO_TOKEN = "dev-only-root-token"  # BOOTSTRAP SECRET (obvious dev value)
APPROLE_NAME = "demo-app"
SECRET_PATH = "secret/data/demo-app/config"
WRAP_TTL = "30s"
WRAP_TTL_SECONDS = 30


def bao_request(path, method="GET", data=None, token=None, wrap_ttl=None):
    """Make an HTTP request to the OpenBao API."""
    url = f"{BAO_ADDR}/v1/{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Vault-Token"] = token
    if wrap_ttl:
        headers["X-Vault-Wrap-TTL"] = wrap_ttl
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"OpenBao {method} {path}: HTTP {e.code} — {error_body}") from e


def run(cmd, **kwargs):
    """Run a command, printing it first."""
    print(f"  $ {cmd if isinstance(cmd, str) else ' '.join(cmd)}")
    result = subprocess.run(cmd, shell=isinstance(cmd, str), cwd=HERE,
                            capture_output=True, text=True, **kwargs)
    if result.stdout.strip():
        for line in result.stdout.strip().split("\n"):
            print(f"    {line}")
    if result.returncode != 0:
        if result.stderr.strip():
            for line in result.stderr.strip().split("\n"):
                print(f"    [stderr] {line}")
        raise RuntimeError(f"Command failed (exit {result.returncode}): {cmd}")
    return result


def wait_for_bao(timeout=30):
    """Wait until OpenBao is ready."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = urllib.request.Request(f"{BAO_ADDR}/v1/sys/health")
            with urllib.request.urlopen(req) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError):
            pass
        time.sleep(0.5)
    raise RuntimeError("OpenBao did not become ready")


def setup_approle():
    """Configure AppRole auth + a KV secret for the demo."""
    print("\n[setup] Enabling AppRole auth method ...")
    try:
        bao_request("sys/auth/approle", method="POST",
                    data={"type": "approle"}, token=BAO_TOKEN)
    except RuntimeError as e:
        if "path is already in use" in str(e):
            pass  # already enabled
        else:
            raise

    print("[setup] Creating AppRole role 'demo-app' ...")
    bao_request(f"auth/approle/role/{APPROLE_NAME}", method="POST", data={
        "token_policies": ["demo-app-policy"],
        "secret_id_ttl": "60s",
        "token_ttl": "300s",
        "token_max_ttl": "600s",
    }, token=BAO_TOKEN)

    print("[setup] Creating policy 'demo-app-policy' ...")
    bao_request("sys/policies/acl/demo-app-policy", method="PUT", data={
        "policy": 'path "secret/data/demo-app/*" { capabilities = ["read"] }'
    }, token=BAO_TOKEN)

    print("[setup] Writing demo secret ...")
    bao_request("secret/data/demo-app/config", method="POST", data={
        "data": {"password": "S3cr3t-Pg-Pass", "host": "db.example.com"}
    }, token=BAO_TOKEN)

    print("[setup] Fetching RoleID ...")
    result = bao_request(f"auth/approle/role/{APPROLE_NAME}/role-id", token=BAO_TOKEN)
    role_id = result["data"]["role_id"]
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    (RUN_DIR / "role-id").write_text(role_id)
    print(f"[setup] RoleID saved to run/role-id")
    return role_id


def test_wrap_and_authenticate():
    """Test 1+2: Deployer wraps SecretID, materializer unwraps and authenticates."""
    print("\n" + "=" * 70)
    print("TEST 1+2: Deployer wraps SecretID → Materializer unwraps + authenticates")
    print("=" * 70)

    # Run the Ansible playbook (the deployer)
    print("\n[deployer] Running Ansible playbook to wrap and deliver SecretID ...")
    env = os.environ.copy()
    env["ANSIBLE_STDOUT_CALLBACK"] = "default"
    env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
    run(["ansible-playbook", "-i", "inventory.yml", "playbook.yml"], env=env)

    # Verify the wrapped token was delivered
    wrapped_token_file = RUN_DIR / "wrapped-token"
    assert wrapped_token_file.exists(), "Wrapped token file was not created"
    wrapping_token = wrapped_token_file.read_text().strip()
    assert len(wrapping_token) > 0, "Wrapped token file is empty"
    print(f"\n[deployer] Wrapped token delivered: {wrapping_token[:8]}...{wrapping_token[-4:]}")

    # Run the materializer (the target)
    print("\n[target] Running materializer — unwrap → login → fetch secret ...")
    env = os.environ.copy()
    env["BAO_ADDR"] = BAO_ADDR
    result = run([sys.executable, "materializer.py"], env=env)

    print("\n[result] Materializer authenticated and fetched secret successfully")
    return wrapping_token


def test_replay_fails(wrapping_token):
    """Test 3: Replay of the same wrapping token fails (single-use)."""
    print("\n" + "=" * 70)
    print("TEST 3: Replay of consumed wrapping token FAILS (single-use property)")
    print("=" * 70)

    print(f"\n[replay] Attempting to unwrap the same token again: {wrapping_token[:8]}...")
    try:
        bao_request("sys/wrapping/unwrap", method="POST", data={}, token=wrapping_token)
        print("[replay] ERROR: unwrap succeeded — this should NOT happen!")
        sys.exit(1)
    except RuntimeError as e:
        if "400" in str(e) or "403" in str(e):
            print(f"[replay] Rejected: {e}")
            print("[replay] PASS: single-use token cannot be replayed")
        else:
            raise


def test_expired_token_fails():
    """Test 4: Expired wrapping token fails (TTL)."""
    print("\n" + "=" * 70)
    print("TEST 4: Expired wrapping token FAILS (TTL property)")
    print("=" * 70)

    # Generate a new wrapped SecretID with a very short TTL (2s)
    print("\n[ttl] Generating a wrapped SecretID with TTL=2s ...")
    result = bao_request(f"auth/approle/role/{APPROLE_NAME}/secret-id", method="POST",
                         data={}, token=BAO_TOKEN, wrap_ttl="2s")
    short_token = result["wrap_info"]["token"]
    print(f"[ttl] Got wrapping token: {short_token[:8]}... (TTL=2s)")

    print("[ttl] Waiting 3s for the token to expire ...")
    time.sleep(3)

    print("[ttl] Attempting to unwrap the expired token ...")
    try:
        bao_request("sys/wrapping/unwrap", method="POST", data={}, token=short_token)
        print("[ttl] ERROR: unwrap succeeded — this should NOT happen!")
        sys.exit(1)
    except RuntimeError as e:
        if "400" in str(e) or "403" in str(e):
            print(f"[ttl] Rejected: {e}")
            print("[ttl] PASS: expired token cannot be unwrapped")
        else:
            raise


def main():
    os.chdir(HERE)

    # Check Docker
    if not shutil.which("docker"):
        print("ERROR: Docker is required for this demo", file=sys.stderr)
        sys.exit(1)

    # Check Ansible
    if not shutil.which("ansible-playbook"):
        print("ERROR: Ansible is required for this demo (pip install ansible)", file=sys.stderr)
        sys.exit(1)

    # Clean run directory
    if RUN_DIR.exists():
        shutil.rmtree(RUN_DIR)
    RUN_DIR.mkdir(parents=True)

    print("AppRole Response-Wrapping Bootstrap Demo")
    print("=" * 70)

    # Bring up OpenBao
    print("\n[infra] Bringing up OpenBao (dev mode) ...")
    subprocess.run(["docker", "compose", "down", "-v"], cwd=HERE,
                   capture_output=True)  # fresh start
    run("docker compose up -d")
    print("[infra] Waiting for OpenBao to be ready ...")
    wait_for_bao()
    print("[infra] OpenBao ready")

    try:
        # Setup AppRole
        setup_approle()

        # Test 1+2: Wrap and authenticate
        wrapping_token = test_wrap_and_authenticate()

        # Test 3: Replay fails
        test_replay_fails(wrapping_token)

        # Test 4: Expired token fails
        test_expired_token_fails()

        print("\n" + "=" * 70)
        print("ALL TESTS PASSED")
        print("  1. Deployer wrapped SecretID via Ansible playbook")
        print("  2. Materializer unwrapped and authenticated via AppRole")
        print("  3. Replay of consumed wrapping token was rejected")
        print("  4. Expired wrapping token was rejected")
        print("=" * 70)

    finally:
        print("\n[infra] Tearing down ...")
        subprocess.run(["docker", "compose", "down", "-v"], cwd=HERE, capture_output=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
