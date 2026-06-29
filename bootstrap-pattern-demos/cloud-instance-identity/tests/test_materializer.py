"""Tests for materializer.py — the cloud identity bootstrap materializer."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# Add parent to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mock_metadata  # noqa: E402
import materializer  # noqa: E402


@pytest.fixture(scope="module")
def metadata_server():
    """Start mock metadata server for tests."""
    srv, thread = mock_metadata.run_server(host="127.0.0.1", port=51171, blocking=False)
    time.sleep(0.3)
    yield srv
    srv.shutdown()


@pytest.fixture(autouse=True)
def env_setup(metadata_server):
    """Set environment for materializer to use our test mock."""
    with patch.dict(os.environ, {
        "AWS_METADATA_URL": "http://127.0.0.1:51171",
        "BAO_ADDR": "http://127.0.0.1:58200",
        "BAO_AUTH_ROLE": "demo-instance-role",
        "BAO_SECRET_PATH": "secret/data/demo/db-password",
    }):
        # Re-import to pick up env changes
        import importlib
        importlib.reload(materializer)
        yield


class TestGetMetadataToken:
    """Test materializer.get_metadata_token()."""

    def test_returns_nonempty_string(self):
        """Should return a non-empty session token."""
        token = materializer.get_metadata_token()
        assert isinstance(token, str)
        assert len(token) > 0

    def test_returns_different_tokens(self):
        """Each call should return a different session token."""
        t1 = materializer.get_metadata_token()
        t2 = materializer.get_metadata_token()
        assert t1 != t2


class TestGetInstanceCredentials:
    """Test materializer.get_instance_credentials()."""

    def test_returns_valid_credentials(self):
        """Should return credentials with expected fields."""
        token = materializer.get_metadata_token()
        creds = materializer.get_instance_credentials(token)
        assert creds["Code"] == "Success"
        assert creds["AccessKeyId"] == mock_metadata.FAKE_ACCESS_KEY
        assert creds["SecretAccessKey"] == mock_metadata.FAKE_SECRET_KEY
        assert "Token" in creds
        assert "Expiration" in creds

    def test_discovers_role_name(self):
        """Should auto-discover the IAM role from the listing endpoint."""
        token = materializer.get_metadata_token()
        creds = materializer.get_instance_credentials(token)
        # If we got here, role discovery worked (it fetches the role name first)
        assert creds["AccessKeyId"] == mock_metadata.FAKE_ACCESS_KEY


class TestWriteSecret:
    """Test materializer.write_secret()."""

    def test_writes_file_with_correct_content(self):
        """Should write JSON secret to the specified file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "sub" / "secret.json"
            with patch.object(materializer, "OUTPUT_FILE", output):
                materializer.write_secret({"password": "S3cr3t-Pg-Pass", "username": "app_user"})
            assert output.exists()
            data = json.loads(output.read_text())
            assert data["password"] == "S3cr3t-Pg-Pass"
            assert data["username"] == "app_user"

    def test_file_mode_is_0600(self):
        """Output file should have mode 0600 (owner read/write only)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "secret.json"
            with patch.object(materializer, "OUTPUT_FILE", output):
                materializer.write_secret({"password": "test"})
            mode = oct(output.stat().st_mode & 0o777)
            assert mode == "0o600"

    def test_creates_parent_directory(self):
        """Should create parent directories if they don't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "deep" / "nested" / "secret.json"
            with patch.object(materializer, "OUTPUT_FILE", output):
                materializer.write_secret({"password": "test"})
            assert output.exists()


class TestNoSecretsOnDisk:
    """Verify that auth tokens don't leak to the output file."""

    def test_output_contains_only_secret_data(self):
        """The written file should contain only the secret payload, not auth tokens."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "secret.json"
            secret = {"password": "S3cr3t-Pg-Pass", "username": "app_user"}
            with patch.object(materializer, "OUTPUT_FILE", output):
                materializer.write_secret(secret)
            content = output.read_text()
            # Should not contain any known auth tokens
            assert "dev-only-root-token" not in content
            assert "hvs." not in content
            # Should contain the secret
            assert "S3cr3t-Pg-Pass" in content
