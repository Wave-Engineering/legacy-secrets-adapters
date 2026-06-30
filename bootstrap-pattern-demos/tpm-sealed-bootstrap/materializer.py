#!/usr/bin/env python3
"""materializer.py — read the TPM-unsealed bootstrap credential and authenticate to OpenBao.

In production this runs as a systemd service with LoadCredentialEncrypted=. At service start,
systemd unseals the TPM-bound blob into $CREDENTIALS_DIRECTORY (a per-service tmpfs, mode 0400).
This script reads from there — never from disk — and uses the credential to authenticate.

The bootstrap credential is an OpenBao token (in this demo: S3cr3t-Pg-Pass as the obvious fake).
"""
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

# Where systemd places unsealed credentials (tmpfs, mode 0400, per-service).
CRED_DIR = os.environ.get("CREDENTIALS_DIRECTORY", "")
CRED_NAME = "bao-token"
BAO_ADDR = os.environ.get("BAO_ADDR", "http://127.0.0.1:58300")


def read_credential() -> str:
    """Read the unsealed credential from $CREDENTIALS_DIRECTORY."""
    if not CRED_DIR:
        print("[materializer] FATAL: $CREDENTIALS_DIRECTORY not set "
              "(are we running under systemd with LoadCredentialEncrypted?)",
              file=sys.stderr)
        sys.exit(1)

    cred_path = Path(CRED_DIR) / CRED_NAME
    if not cred_path.exists():
        print(f"[materializer] FATAL: credential '{CRED_NAME}' not found in "
              f"$CREDENTIALS_DIRECTORY ({CRED_DIR})", file=sys.stderr)
        sys.exit(1)

    token = cred_path.read_text().strip()
    if not token:
        print(f"[materializer] FATAL: credential '{CRED_NAME}' is empty", file=sys.stderr)
        sys.exit(1)

    return token


def authenticate_to_openbao(token: str) -> bool:
    """Authenticate to OpenBao using the unsealed token. Returns True on success."""
    url = f"{BAO_ADDR}/v1/auth/token/lookup-self"
    req = urllib.request.Request(url, headers={"X-Vault-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            display_name = data.get("data", {}).get("display_name", "unknown")
            print(f"[materializer] authenticated to OpenBao as '{display_name}'")
            return True
    except urllib.error.HTTPError as e:
        print(f"[materializer] FATAL: OpenBao rejected the token (HTTP {e.code})",
              file=sys.stderr)
        return False
    except urllib.error.URLError as e:
        print(f"[materializer] FATAL: cannot reach OpenBao at {BAO_ADDR}: {e.reason}",
              file=sys.stderr)
        return False


def main() -> int:
    token = read_credential()
    print(f"[materializer] read credential '{CRED_NAME}' from $CREDENTIALS_DIRECTORY "
          f"({len(token)} chars, never printed)")
    if authenticate_to_openbao(token):
        print("[materializer] bootstrap complete — credential never touched disk")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
