"""Tests for mock_metadata.py — the IMDSv2 simulator."""
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

# Add parent to path so we can import the module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mock_metadata  # noqa: E402


@pytest.fixture(scope="module")
def server():
    """Start mock metadata server for the test module."""
    srv, thread = mock_metadata.run_server(host="127.0.0.1", port=51170, blocking=False)
    time.sleep(0.3)  # let it bind
    yield srv
    srv.shutdown()


BASE = "http://127.0.0.1:51170"


class TestIMDSv2Flow:
    """Test the two-step IMDSv2 flow."""

    def test_put_token_returns_session_token(self, server):
        """PUT /latest/api/token with TTL header returns a session token."""
        req = Request(
            f"{BASE}/latest/api/token",
            method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "300"},
        )
        with urlopen(req, timeout=5) as resp:
            token = resp.read().decode()
        assert len(token) == 64  # hex(32 bytes) = 64 chars
        assert resp.status == 200

    def test_put_token_requires_ttl_header(self, server):
        """PUT without the TTL header returns 400."""
        req = Request(f"{BASE}/latest/api/token", method="PUT")
        with pytest.raises(HTTPError) as exc_info:
            urlopen(req, timeout=5)
        assert exc_info.value.code == 400

    def test_get_without_token_returns_401(self, server):
        """GET without X-aws-ec2-metadata-token header returns 401."""
        req = Request(f"{BASE}/latest/meta-data/iam/security-credentials/")
        with pytest.raises(HTTPError) as exc_info:
            urlopen(req, timeout=5)
        assert exc_info.value.code == 401

    def test_get_with_invalid_token_returns_401(self, server):
        """GET with an invalid session token returns 401."""
        req = Request(
            f"{BASE}/latest/meta-data/iam/security-credentials/",
            headers={"X-aws-ec2-metadata-token": "invalid-token"},
        )
        with pytest.raises(HTTPError) as exc_info:
            urlopen(req, timeout=5)
        assert exc_info.value.code == 401

    def test_full_flow_role_listing(self, server):
        """Full flow: PUT token, then GET role listing."""
        # Get session token
        req = Request(
            f"{BASE}/latest/api/token",
            method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "300"},
        )
        with urlopen(req, timeout=5) as resp:
            token = resp.read().decode()

        # List roles
        req = Request(
            f"{BASE}/latest/meta-data/iam/security-credentials/",
            headers={"X-aws-ec2-metadata-token": token},
        )
        with urlopen(req, timeout=5) as resp:
            role = resp.read().decode()
        assert role == "demo-instance-role"

    def test_full_flow_credentials(self, server):
        """Full flow: PUT token, then GET credentials for the role."""
        # Get session token
        req = Request(
            f"{BASE}/latest/api/token",
            method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "300"},
        )
        with urlopen(req, timeout=5) as resp:
            token = resp.read().decode()

        # Get credentials
        req = Request(
            f"{BASE}/latest/meta-data/iam/security-credentials/{mock_metadata.IAM_ROLE}",
            headers={"X-aws-ec2-metadata-token": token},
        )
        with urlopen(req, timeout=5) as resp:
            creds = json.loads(resp.read().decode())

        assert creds["Code"] == "Success"
        assert creds["AccessKeyId"] == mock_metadata.FAKE_ACCESS_KEY
        assert creds["SecretAccessKey"] == mock_metadata.FAKE_SECRET_KEY
        assert "Token" in creds
        assert "Expiration" in creds

    def test_token_expiry(self, server):
        """A session token with TTL=1 should expire after 1 second."""
        req = Request(
            f"{BASE}/latest/api/token",
            method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "1"},
        )
        with urlopen(req, timeout=5) as resp:
            token = resp.read().decode()

        # Should work immediately
        req = Request(
            f"{BASE}/latest/meta-data/iam/security-credentials/",
            headers={"X-aws-ec2-metadata-token": token},
        )
        with urlopen(req, timeout=5) as resp:
            assert resp.status == 200

        # Wait for expiry
        time.sleep(1.5)

        # Should now fail
        req = Request(
            f"{BASE}/latest/meta-data/iam/security-credentials/",
            headers={"X-aws-ec2-metadata-token": token},
        )
        with pytest.raises(HTTPError) as exc_info:
            urlopen(req, timeout=5)
        assert exc_info.value.code == 401

    def test_rotation_different_tokens(self, server):
        """Each credential fetch returns a different STS session token."""
        tokens = []
        for _ in range(3):
            req = Request(
                f"{BASE}/latest/api/token",
                method="PUT",
                headers={"X-aws-ec2-metadata-token-ttl-seconds": "300"},
            )
            with urlopen(req, timeout=5) as resp:
                session_token = resp.read().decode()

            req = Request(
                f"{BASE}/latest/meta-data/iam/security-credentials/{mock_metadata.IAM_ROLE}",
                headers={"X-aws-ec2-metadata-token": session_token},
            )
            with urlopen(req, timeout=5) as resp:
                creds = json.loads(resp.read().decode())
            tokens.append(creds["Token"])

        # All tokens should be different (rotation)
        assert len(set(tokens)) == 3

    def test_nonexistent_path_returns_404(self, server):
        """GET for a non-existent path returns 404."""
        req = Request(
            f"{BASE}/latest/api/token",
            method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "300"},
        )
        with urlopen(req, timeout=5) as resp:
            token = resp.read().decode()

        req = Request(
            f"{BASE}/latest/meta-data/nonexistent",
            headers={"X-aws-ec2-metadata-token": token},
        )
        with pytest.raises(HTTPError) as exc_info:
            urlopen(req, timeout=5)
        assert exc_info.value.code == 404
