"""Unit tests for materializer.py — mocks the OpenBao API to test logic."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError
from io import BytesIO

# Add the pattern directory to sys.path
PATTERN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PATTERN_DIR))

import materializer


class TestBaoRequest(unittest.TestCase):
    """Test the bao_request helper."""

    @patch("materializer.urllib.request.urlopen")
    def test_successful_get(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"data": {"key": "value"}}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = materializer.bao_request("secret/data/test", token="tok")
        self.assertEqual(result, {"data": {"key": "value"}})

    @patch("materializer.urllib.request.urlopen")
    def test_http_error_raises(self, mock_urlopen):
        error = HTTPError("http://x", 403, "Forbidden", {}, BytesIO(b'{"errors":["permission denied"]}'))
        mock_urlopen.side_effect = error

        with self.assertRaises(RuntimeError) as ctx:
            materializer.bao_request("secret/data/test", token="tok")
        self.assertIn("403", str(ctx.exception))


class TestUnwrapToken(unittest.TestCase):
    """Test the unwrap_token function."""

    @patch("materializer.bao_request")
    def test_unwrap_returns_secret_id(self, mock_req):
        mock_req.return_value = {"data": {"secret_id": "s-abc123"}}
        result = materializer.unwrap_token("wrap-token-xyz")
        mock_req.assert_called_once_with(
            "sys/wrapping/unwrap", method="POST", data={}, token="wrap-token-xyz"
        )
        self.assertEqual(result, "s-abc123")


class TestApproleLogin(unittest.TestCase):
    """Test the approle_login function."""

    @patch("materializer.bao_request")
    def test_login_returns_client_token(self, mock_req):
        mock_req.return_value = {"auth": {"client_token": "s.client-token-abc"}}
        result = materializer.approle_login("role-id-123", "secret-id-456")
        mock_req.assert_called_once_with(
            "auth/approle/login", method="POST", data={
                "role_id": "role-id-123",
                "secret_id": "secret-id-456",
            }
        )
        self.assertEqual(result, "s.client-token-abc")


class TestFetchSecret(unittest.TestCase):
    """Test the fetch_secret function."""

    @patch("materializer.bao_request")
    def test_fetch_returns_data(self, mock_req):
        mock_req.return_value = {"data": {"data": {"password": "S3cr3t-Pg-Pass", "host": "db"}}}
        result = materializer.fetch_secret("tok", "secret/data/demo-app/config")
        mock_req.assert_called_once_with("secret/data/demo-app/config", token="tok")
        self.assertEqual(result, {"password": "S3cr3t-Pg-Pass", "host": "db"})


class TestMain(unittest.TestCase):
    """Test the main orchestration."""

    @patch("materializer.fetch_secret")
    @patch("materializer.approle_login")
    @patch("materializer.unwrap_token")
    def test_main_happy_path(self, mock_unwrap, mock_login, mock_fetch, tmp_path=None):
        """Test main orchestrates unwrap -> login -> fetch correctly."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            role_id_file = run_dir / "role-id"
            wrapped_token_file = run_dir / "wrapped-token"
            role_id_file.write_text("role-id-abc")
            wrapped_token_file.write_text("wrap-token-xyz")

            with patch.object(materializer, "ROLE_ID_FILE", role_id_file), \
                 patch.object(materializer, "WRAPPED_TOKEN_FILE", wrapped_token_file):
                mock_unwrap.return_value = "secret-id-123"
                mock_login.return_value = "client-token-abc"
                mock_fetch.return_value = {"password": "S3cr3t-Pg-Pass"}

                result = materializer.main()

                mock_unwrap.assert_called_once_with("wrap-token-xyz")
                mock_login.assert_called_once_with("role-id-abc", "secret-id-123")
                mock_fetch.assert_called_once_with("client-token-abc", materializer.SECRET_PATH)
                self.assertEqual(result, {"password": "S3cr3t-Pg-Pass"})

    def test_main_missing_role_id(self):
        """Test main exits if role-id file is missing."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            role_id_file = run_dir / "role-id"  # does not exist
            wrapped_token_file = run_dir / "wrapped-token"
            wrapped_token_file.write_text("wrap-token-xyz")

            with patch.object(materializer, "ROLE_ID_FILE", role_id_file), \
                 patch.object(materializer, "WRAPPED_TOKEN_FILE", wrapped_token_file):
                with self.assertRaises(SystemExit):
                    materializer.main()

    def test_main_missing_wrapped_token(self):
        """Test main exits if wrapped-token file is missing."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            role_id_file = run_dir / "role-id"
            role_id_file.write_text("role-id-abc")
            wrapped_token_file = run_dir / "wrapped-token"  # does not exist

            with patch.object(materializer, "ROLE_ID_FILE", role_id_file), \
                 patch.object(materializer, "WRAPPED_TOKEN_FILE", wrapped_token_file):
                with self.assertRaises(SystemExit):
                    materializer.main()


if __name__ == "__main__":
    unittest.main()
