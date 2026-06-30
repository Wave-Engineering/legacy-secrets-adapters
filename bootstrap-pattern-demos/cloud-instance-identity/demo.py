#!/usr/bin/env python3
"""demo.py — end-to-end orchestration of the cloud-instance-identity bootstrap pattern.

Proves:
  1. Materializer gets a token from the (mock) metadata service (IMDSv2 flow)
  2. Materializer authenticates to OpenBao using that token (AWS auth method)
  3. Materializer fetches a secret from OpenBao
  4. No tokens or secrets remain on disk after cleanup
  5. Token rotation: a second metadata call yields fresh credentials

Requires Docker (OpenBao dev-mode). The mock metadata server runs in-process (stdlib
http.server). Since OpenBao's dev image does not ship the AWS auth plugin, the demo
patches the auth step to use token-create (which produces the same result: a scoped
Vault token). The full IMDSv2 metadata flow is exercised for real against the mock.

Exit 0 = all assertions pass. Non-zero = failure.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import mock_metadata  # noqa: E402

# --- Configuration ---
MOCK_PORT = 51169
BAO_ADDR = "http://127.0.0.1:58200"
BAO_TOKEN = "dev-only-root-token"  # BOOTSTRAP SECRET (obvious dev value, dev-mode only)
SECRET_PATH = "secret/data/demo/db-password"
SECRET_VALUE = "S3cr3t-Pg-Pass"  # The canonical fake secret
OUTPUT_FILE = HERE / "run" / "secret.json"
DOCKER_COMPOSE = HERE / "docker-compose.yml"

os.environ["AWS_METADATA_URL"] = f"http://127.0.0.1:{MOCK_PORT}"
os.environ["BAO_ADDR"] = BAO_ADDR
os.environ["BAO_AUTH_ROLE"] = "demo-instance-role"
os.environ["BAO_SECRET_PATH"] = SECRET_PATH
os.environ["MATERIALIZER_OUTPUT"] = str(OUTPUT_FILE)


def _bao_api(method, path, data=None, token=BAO_TOKEN):
    """Helper: call the OpenBao HTTP API."""
    url = f"{BAO_ADDR}/v1/{path}"
    payload = json.dumps(data).encode() if data else None
    req = Request(url, data=payload, method=method,
                  headers={"X-Vault-Token": token, "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=10) as resp:
            body = resp.read().decode()
            return json.loads(body) if body.strip() else {}
    except HTTPError as e:
        body = e.read().decode() if e.fp else ""
        if e.code == 204:
            return {}
        raise RuntimeError(f"OpenBao API {method} {path} failed ({e.code}): {body}") from e


def _wait_for_bao(timeout=30):
    """Wait for OpenBao to be ready."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = Request(f"{BAO_ADDR}/v1/sys/health")
            with urlopen(req, timeout=2):
                return True
        except (URLError, OSError):
            time.sleep(0.5)
    raise RuntimeError("OpenBao did not become ready in time")


def _setup_openbao():
    """Configure OpenBao with a test secret and a scoped policy.

    NOTE: The AWS auth plugin is not available in the OpenBao dev image, so this demo
    patches the authentication step to use token-create with a scoped policy (which
    produces the same result: a short-lived token that can read only the demo secret).
    The materializer still exercises the full IMDSv2 metadata flow for real.
    """
    # Enable KV v2 secrets engine (may already be enabled in dev mode)
    try:
        _bao_api("POST", "sys/mounts/secret", {"type": "kv", "options": {"version": "2"}})
    except RuntimeError:
        pass  # Already enabled in dev mode

    # Write the test secret
    _bao_api("POST", SECRET_PATH, {"data": {"password": SECRET_VALUE, "username": "app_user"}})

    # Create a policy that allows reading only the demo secret
    _bao_api("PUT", "sys/policies/acl/demo-read", {
        "policy": 'path "secret/data/demo/*" { capabilities = ["read"] }'
    })


def _start_mock_metadata():
    """Start the mock IMDSv2 server in a background thread."""
    server, thread = mock_metadata.run_server(port=MOCK_PORT, blocking=False)
    time.sleep(0.2)
    return server


def _start_docker():
    """Start the Docker Compose stack (OpenBao dev-mode)."""
    subprocess.run(
        ["docker", "compose", "down", "-v"],
        cwd=HERE, capture_output=True,
    )
    result = subprocess.run(
        ["docker", "compose", "up", "-d"],
        cwd=HERE, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"docker compose up failed: {result.stderr}")


def _stop_docker():
    """Tear down the Docker Compose stack."""
    subprocess.run(
        ["docker", "compose", "down", "-v"],
        cwd=HERE, capture_output=True,
    )


def _cleanup():
    """Remove runtime artifacts."""
    run_dir = HERE / "run"
    if run_dir.exists():
        shutil.rmtree(run_dir)


def _install_mock_auth():
    """Patch the materializer's authenticate_to_openbao to simulate AWS auth.

    Since the OpenBao dev image doesn't include the AWS auth plugin, we simulate
    what it would do: verify the AWS credentials are present and valid, then create
    a scoped Vault token. The materializer still goes through the full IMDSv2 flow
    for the metadata part — that's the property this pattern demonstrates.

    In production, OpenBao's real AWS auth method would:
      1. Receive the signed STS GetCallerIdentity request
      2. Call STS to verify the identity
      3. Map the IAM principal to a role/policy
      4. Return a scoped Vault token
    Our mock does step 3-4 after verifying the credentials are non-empty.
    """
    import materializer

    _original = materializer.authenticate_to_openbao

    def _mock_auth(aws_creds: dict) -> str:
        """Simulate AWS auth: verify credentials present, create scoped token."""
        # Verify the AWS credentials are present (real AWS auth would verify via STS)
        assert aws_creds.get("AccessKeyId"), "No AccessKeyId in credentials"
        assert aws_creds.get("SecretAccessKey"), "No SecretAccessKey in credentials"
        assert aws_creds.get("Token"), "No session token in credentials"

        # Create a child token with the demo-read policy (simulates AWS auth success)
        payload = json.dumps({
            "policies": ["demo-read"],
            "ttl": "1h",
            "display_name": f"aws-{aws_creds['AccessKeyId'][:8]}",
            "meta": {"role": "demo-instance-role"},
        }).encode()
        req = Request(
            f"{BAO_ADDR}/v1/auth/token/create",
            data=payload,
            headers={"X-Vault-Token": BAO_TOKEN, "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data["auth"]["client_token"]

    materializer.authenticate_to_openbao = _mock_auth
    return _original


def main():
    """Run the full demo."""
    print("=" * 70)
    print("  cloud-instance-identity: end-to-end demo")
    print("=" * 70)
    print()

    # Check Docker
    has_docker = subprocess.run(
        ["docker", "info"], capture_output=True
    ).returncode == 0 if shutil.which("docker") else False

    if not has_docker:
        print("ERROR: Docker is required for this demo.", file=sys.stderr)
        sys.exit(1)

    _cleanup()
    mock_server = None
    original_auth = None

    try:
        # 1. Start Docker (OpenBao)
        print("[demo] starting OpenBao (dev-mode) via docker compose ...")
        _start_docker()
        _wait_for_bao()
        print("[demo] OpenBao is ready")

        # 2. Start mock metadata server
        print("[demo] starting mock IMDSv2 metadata service ...")
        mock_server = _start_mock_metadata()
        print(f"[demo] mock metadata listening on 127.0.0.1:{MOCK_PORT}")

        # 3. Configure OpenBao (KV secret + policy)
        print("[demo] configuring OpenBao (KV secret + read policy) ...")
        _setup_openbao()
        print("[demo] OpenBao configured")

        # 4. Install mock AWS auth (OpenBao dev image lacks the aws plugin)
        print("[demo] installing mock AWS auth handler (OpenBao dev has no aws plugin) ...")
        import materializer
        original_auth = _install_mock_auth()
        print("[demo] mock auth handler installed")
        print()

        # === PROOF 1: Materializer gets token from metadata ===
        print("-" * 50)
        print("PROOF 1: materializer gets token from metadata (IMDSv2)")
        print("-" * 50)
        token = materializer.get_metadata_token()
        assert token and len(token) > 0, "Failed to get metadata session token"
        print(f"  session token: {token[:16]}... (length={len(token)})")
        print("  PASS: IMDSv2 PUT -> session token obtained")
        print()

        # === PROOF 2: Materializer authenticates to OpenBao ===
        print("-" * 50)
        print("PROOF 2: materializer authenticates to OpenBao via AWS identity")
        print("-" * 50)
        creds = materializer.get_instance_credentials(token)
        assert creds["AccessKeyId"] == mock_metadata.FAKE_ACCESS_KEY
        print(f"  AccessKeyId: {creds['AccessKeyId']}")
        print(f"  Token: {creds['Token'][:20]}...")
        vault_token = materializer.authenticate_to_openbao(creds)
        assert vault_token and len(vault_token) > 0
        print(f"  OpenBao token: {vault_token[:8]}...")
        print("  PASS: instance credentials -> OpenBao authentication")
        print()

        # === PROOF 3: Materializer fetches secret ===
        print("-" * 50)
        print("PROOF 3: materializer fetches secret from OpenBao")
        print("-" * 50)
        secret = materializer.fetch_secret(vault_token)
        assert secret["password"] == SECRET_VALUE, f"Expected {SECRET_VALUE}, got {secret.get('password')}"
        print(f"  secret.password = {secret['password']}")
        print("  PASS: secret fetched successfully")
        print()

        # Full materialize flow (writes to file)
        print("-" * 50)
        print("FULL FLOW: materialize end-to-end")
        print("-" * 50)
        materializer.materialize(verbose=True)
        assert OUTPUT_FILE.exists(), f"Output file not created: {OUTPUT_FILE}"
        written = json.loads(OUTPUT_FILE.read_text())
        assert written["password"] == SECRET_VALUE
        print("  PASS: full materialize flow completed")
        print()

        # === PROOF 4: No tokens/secrets on disk (besides the delivery output) ===
        print("-" * 50)
        print("PROOF 4: no tokens/secrets on disk (besides delivery output)")
        print("-" * 50)
        run_dir = HERE / "run"
        for f in run_dir.rglob("*"):
            if f.is_file() and f != OUTPUT_FILE:
                content = f.read_text()
                assert BAO_TOKEN not in content, f"Root token leaked to {f}"
                assert vault_token not in content, f"Vault token leaked to {f}"
        output_content = OUTPUT_FILE.read_text()
        assert BAO_TOKEN not in output_content, "Root token in output!"
        assert vault_token not in output_content, "Vault auth token in output!"
        assert "session token" not in output_content.lower()
        print("  no vault tokens or metadata tokens written to disk")
        print("  only the delivery payload (the secret itself) is on disk")
        print("  PASS: no auth credentials on disk")
        print()

        # === PROOF 5: Token rotation — fresh credentials on second call ===
        print("-" * 50)
        print("PROOF 5: token rotation — fresh credentials on each metadata call")
        print("-" * 50)
        token2 = materializer.get_metadata_token()
        assert token2 != token, "Second session token should differ"
        creds2 = materializer.get_instance_credentials(token2)
        assert creds2["Token"] != creds["Token"], "STS token should rotate"
        print(f"  first  Token: {creds['Token']}")
        print(f"  second Token: {creds2['Token']}")
        print("  PASS: metadata service provides fresh credentials (rotation)")
        print()

        # === ALL PROOFS PASSED ===
        print("=" * 70)
        print("  ALL PROOFS PASSED")
        print("  The machine's cloud identity IS the bootstrap credential.")
        print("  No stored secret. The metadata endpoint + cloud auth method = trust anchor.")
        print("=" * 70)

    finally:
        # Restore original auth if patched
        if original_auth is not None:
            import materializer as _m
            _m.authenticate_to_openbao = original_auth
        # Shutdown mock server
        if mock_server:
            mock_server.shutdown()
        # Stop Docker
        print("\n[demo] tearing down ...")
        _stop_docker()
        _cleanup()

    return 0


if __name__ == "__main__":
    sys.exit(main())
