"""Tests for materializer.py — the credential reader and OpenBao authenticator."""
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import materializer  # noqa: E402


class TestReadCredential:
    """Test the read_credential() function."""

    def test_missing_credentials_directory_env(self):
        """Exits with error if $CREDENTIALS_DIRECTORY is not set."""
        with mock.patch.dict(os.environ, {}, clear=True):
            # Remove CREDENTIALS_DIRECTORY if present
            os.environ.pop("CREDENTIALS_DIRECTORY", None)
            with mock.patch.object(materializer, "CRED_DIR", ""):
                with pytest.raises(SystemExit):
                    materializer.read_credential()

    def test_missing_credential_file(self, tmp_path):
        """Exits with error if the credential file doesn't exist."""
        with mock.patch.object(materializer, "CRED_DIR", str(tmp_path)):
            with pytest.raises(SystemExit):
                materializer.read_credential()

    def test_empty_credential_file(self, tmp_path):
        """Exits with error if the credential file is empty."""
        cred_file = tmp_path / "bao-token"
        cred_file.write_text("")
        with mock.patch.object(materializer, "CRED_DIR", str(tmp_path)):
            with pytest.raises(SystemExit):
                materializer.read_credential()

    def test_reads_credential_successfully(self, tmp_path):
        """Reads the credential from $CREDENTIALS_DIRECTORY."""
        cred_file = tmp_path / "bao-token"
        cred_file.write_text("S3cr3t-Pg-Pass")
        with mock.patch.object(materializer, "CRED_DIR", str(tmp_path)):
            token = materializer.read_credential()
        assert token == "S3cr3t-Pg-Pass"

    def test_strips_whitespace(self, tmp_path):
        """Strips trailing whitespace/newlines from the credential."""
        cred_file = tmp_path / "bao-token"
        cred_file.write_text("S3cr3t-Pg-Pass\n")
        with mock.patch.object(materializer, "CRED_DIR", str(tmp_path)):
            token = materializer.read_credential()
        assert token == "S3cr3t-Pg-Pass"


class TestAuthenticateToOpenbao:
    """Test the authenticate_to_openbao() function."""

    def test_successful_auth(self):
        """Returns True on successful OpenBao authentication."""
        response_data = b'{"data": {"display_name": "token"}}'
        with mock.patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = mock.MagicMock()
            mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = mock.MagicMock(return_value=False)
            mock_resp.read.return_value = response_data
            mock_urlopen.return_value = mock_resp
            assert materializer.authenticate_to_openbao("test-token") is True

    def test_rejected_token(self):
        """Returns False when OpenBao rejects the token."""
        import urllib.error
        with mock.patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url="http://test", code=403, msg="Forbidden",
                hdrs=None, fp=None)
            assert materializer.authenticate_to_openbao("bad-token") is False

    def test_unreachable_server(self):
        """Returns False when OpenBao is unreachable."""
        import urllib.error
        with mock.patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
            assert materializer.authenticate_to_openbao("token") is False


class TestMain:
    """Test the main() entry point."""

    def test_successful_flow(self, tmp_path):
        """Returns 0 on full successful flow."""
        cred_file = tmp_path / "bao-token"
        cred_file.write_text("test-token")
        response_data = b'{"data": {"display_name": "token"}}'
        with mock.patch.object(materializer, "CRED_DIR", str(tmp_path)):
            with mock.patch("urllib.request.urlopen") as mock_urlopen:
                mock_resp = mock.MagicMock()
                mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
                mock_resp.__exit__ = mock.MagicMock(return_value=False)
                mock_resp.read.return_value = response_data
                mock_urlopen.return_value = mock_resp
                result = materializer.main()
        assert result == 0

    def test_auth_failure_returns_1(self, tmp_path):
        """Returns 1 when authentication fails."""
        cred_file = tmp_path / "bao-token"
        cred_file.write_text("bad-token")
        import urllib.error
        with mock.patch.object(materializer, "CRED_DIR", str(tmp_path)):
            with mock.patch("urllib.request.urlopen") as mock_urlopen:
                mock_urlopen.side_effect = urllib.error.HTTPError(
                    url="http://test", code=403, msg="Forbidden",
                    hdrs=None, fp=None)
                result = materializer.main()
        assert result == 1
