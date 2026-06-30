#!/usr/bin/env python3
"""materializer.py — authenticate to OpenBao using cloud instance identity.

This is the bootstrap-secret materializer: it calls the (mock) EC2 metadata endpoint to
get short-lived AWS credentials, then uses those credentials to authenticate to OpenBao
via the AWS auth method. Once authenticated, it fetches a secret from OpenBao and writes
it to a file (the delivery-pattern handoff point).

Flow:
  1. PUT /latest/api/token  → get IMDSv2 session token
  2. GET /latest/meta-data/iam/security-credentials/<role>  → get AWS creds
  3. POST to OpenBao /v1/auth/aws/login with the AWS identity
  4. Read a secret from OpenBao using the resulting Vault token
  5. Write the secret to the delivery file (no secrets on disk besides the transient output)

The machine's identity IS the bootstrap credential — no stored secret required.
"""
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent

# Configuration (env vars let demo.py override for the mock)
METADATA_URL = os.environ.get("AWS_METADATA_URL", "http://169.254.169.254")
BAO_ADDR = os.environ.get("BAO_ADDR", "http://127.0.0.1:58200")
BAO_ROLE = os.environ.get("BAO_AUTH_ROLE", "demo-instance-role")
SECRET_PATH = os.environ.get("BAO_SECRET_PATH", "secret/data/demo/db-password")
OUTPUT_FILE = Path(os.environ.get("MATERIALIZER_OUTPUT", str(HERE / "run" / "secret.json")))


def get_metadata_token(ttl: int = 21600) -> str:
    """Step 1: PUT to get an IMDSv2 session token."""
    req = Request(
        f"{METADATA_URL}/latest/api/token",
        method="PUT",
        headers={"X-aws-ec2-metadata-token-ttl-seconds": str(ttl)},
    )
    with urlopen(req, timeout=5) as resp:
        return resp.read().decode()


def get_instance_credentials(session_token: str) -> dict:
    """Step 2: GET IAM credentials from the metadata service."""
    # First discover the role name
    req = Request(
        f"{METADATA_URL}/latest/meta-data/iam/security-credentials/",
        headers={"X-aws-ec2-metadata-token": session_token},
    )
    with urlopen(req, timeout=5) as resp:
        role_name = resp.read().decode().strip()

    # Then fetch the credentials for that role
    req = Request(
        f"{METADATA_URL}/latest/meta-data/iam/security-credentials/{role_name}",
        headers={"X-aws-ec2-metadata-token": session_token},
    )
    with urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode())


def authenticate_to_openbao(aws_creds: dict) -> str:
    """Step 3: Authenticate to OpenBao via the AWS auth method.

    In a real deployment this would use STS GetCallerIdentity signed headers.
    For the demo, we pass the credentials directly to a simplified AWS auth endpoint
    that the demo configures to trust our mock metadata.
    """
    payload = json.dumps({
        "role": BAO_ROLE,
        "iam_http_request_method": "POST",
        "iam_request_url": "aHR0cHM6Ly9zdHMuYW1hem9uYXdzLmNvbS8=",  # base64("https://sts.amazonaws.com/")
        "iam_request_body": "QWN0aW9uPUdldENhbGxlcklkZW50aXR5JlZlcnNpb249MjAxMS0wNi0xNQ==",  # base64 STS body
        "iam_request_headers": json.dumps({
            "Authorization": [f"AWS4-HMAC-SHA256 Credential={aws_creds['AccessKeyId']}"],
            "X-Amz-Security-Token": [aws_creds.get("Token", "")],
        }),
    }).encode()

    req = Request(
        f"{BAO_ADDR}/v1/auth/aws/login",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
        return data["auth"]["client_token"]


def fetch_secret(vault_token: str) -> dict:
    """Step 4: Read a secret from OpenBao."""
    req = Request(
        f"{BAO_ADDR}/v1/{SECRET_PATH}",
        headers={"X-Vault-Token": vault_token},
    )
    with urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode())
        # KV v2 nests under data.data; KV v1 just under data
        if "data" in data.get("data", {}):
            return data["data"]["data"]
        return data["data"]


def write_secret(secret: dict) -> None:
    """Step 5: Write the secret to the output file (delivery handoff)."""
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(OUTPUT_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.write(fd, (json.dumps(secret, indent=2) + "\n").encode())
    os.close(fd)


def materialize(verbose: bool = True) -> dict:
    """Full materializer flow: metadata → OpenBao auth → fetch secret → write."""
    if verbose:
        print("[materializer] requesting IMDSv2 session token ...")
    token = get_metadata_token()
    if verbose:
        print("[materializer] got session token; fetching instance credentials ...")

    creds = get_instance_credentials(token)
    if verbose:
        print(f"[materializer] got credentials for role (AccessKeyId={creds['AccessKeyId'][:8]}...)")

    if verbose:
        print("[materializer] authenticating to OpenBao via AWS auth method ...")
    vault_token = authenticate_to_openbao(creds)
    if verbose:
        print(f"[materializer] authenticated (token={vault_token[:8]}...)")

    if verbose:
        print(f"[materializer] reading secret from {SECRET_PATH} ...")
    secret = fetch_secret(vault_token)
    if verbose:
        print(f"[materializer] got secret; writing to {OUTPUT_FILE.relative_to(HERE)} ...")

    write_secret(secret)
    if verbose:
        print(f"[materializer] done — secret materialized to {OUTPUT_FILE.relative_to(HERE)} (mode 0600)")
    return secret


if __name__ == "__main__":
    try:
        materialize()
    except (HTTPError, URLError, KeyError) as e:
        print(f"[materializer] ERROR: {e}", file=sys.stderr)
        sys.exit(1)
