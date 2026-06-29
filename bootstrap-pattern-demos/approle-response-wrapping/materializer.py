#!/usr/bin/env python3
"""materializer.py — unwraps a response-wrapped token, authenticates via AppRole, fetches a secret.

This is the TARGET side of the bootstrap: the materializer receives a single-use wrapping
token (delivered by the Ansible playbook), unwraps it to obtain a SecretID, authenticates
to OpenBao via AppRole (RoleID + SecretID), and fetches the actual secret.

The wrapping token is consumed on first unwrap — replay is impossible.
"""
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAO_ADDR = os.environ.get("BAO_ADDR", "http://127.0.0.1:58201")
ROLE_ID_FILE = HERE / "run" / "role-id"
WRAPPED_TOKEN_FILE = HERE / "run" / "wrapped-token"
SECRET_PATH = "secret/data/demo-app/config"


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
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"OpenBao {method} {path}: HTTP {e.code} — {error_body}") from e


def unwrap_token(wrapping_token):
    """Unwrap a response-wrapped token to retrieve the SecretID."""
    result = bao_request("sys/wrapping/unwrap", method="POST", data={}, token=wrapping_token)
    return result["data"]["secret_id"]


def approle_login(role_id, secret_id):
    """Authenticate via AppRole and return the client token."""
    result = bao_request("auth/approle/login", method="POST", data={
        "role_id": role_id,
        "secret_id": secret_id,
    })
    return result["auth"]["client_token"]


def fetch_secret(client_token, path):
    """Fetch a secret from the KV v2 secrets engine."""
    result = bao_request(path, token=client_token)
    return result["data"]["data"]


def main():
    """Orchestrate: unwrap → login → fetch secret."""
    # Read the RoleID (this is the non-secret half — safe to store)
    if not ROLE_ID_FILE.exists():
        print(f"[materializer] ERROR: role-id not found at {ROLE_ID_FILE}", file=sys.stderr)
        sys.exit(1)
    role_id = ROLE_ID_FILE.read_text().strip()

    # Read the wrapped token (single-use, delivered by the deployer)
    if not WRAPPED_TOKEN_FILE.exists():
        print(f"[materializer] ERROR: wrapped-token not found at {WRAPPED_TOKEN_FILE}", file=sys.stderr)
        sys.exit(1)
    wrapping_token = WRAPPED_TOKEN_FILE.read_text().strip()

    # Step 1: Unwrap to get the SecretID
    print(f"[materializer] unwrapping token to obtain SecretID ...")
    secret_id = unwrap_token(wrapping_token)
    print(f"[materializer] SecretID obtained (single-use token consumed)")

    # Step 2: Authenticate via AppRole
    print(f"[materializer] authenticating via AppRole (RoleID + SecretID) ...")
    client_token = approle_login(role_id, secret_id)
    print(f"[materializer] authenticated — got client token")

    # Step 3: Fetch the actual secret
    print(f"[materializer] fetching secret from {SECRET_PATH} ...")
    secret_data = fetch_secret(client_token, SECRET_PATH)
    print(f"[materializer] secret retrieved: keys={list(secret_data.keys())}")
    print(f"[materializer] (password used in memory — never printed, never logged)")

    return secret_data


if __name__ == "__main__":
    main()
