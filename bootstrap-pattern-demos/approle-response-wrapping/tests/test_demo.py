"""Unit tests for demo.py — mocks Docker/Ansible/OpenBao to test orchestration logic."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, call
from urllib.error import HTTPError
from io import BytesIO

# Add the pattern directory to sys.path
PATTERN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PATTERN_DIR))

import demo


class TestBaoRequest(unittest.TestCase):
    """Test demo.bao_request (same shape as materializer's, tested independently)."""

    @patch("demo.urllib.request.urlopen")
    def test_successful_post(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"data": {"role_id": "rid"}}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = demo.bao_request("auth/approle/role/demo-app/role-id", token="tok")
        self.assertEqual(result, {"data": {"role_id": "rid"}})

    @patch("demo.urllib.request.urlopen")
    def test_wrap_ttl_header(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"wrap_info": {"token": "t"}}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        demo.bao_request("auth/approle/role/demo-app/secret-id", method="POST",
                         data={}, token="tok", wrap_ttl="30s")
        req_obj = mock_urlopen.call_args[0][0]
        self.assertEqual(req_obj.get_header("X-vault-wrap-ttl"), "30s")

    @patch("demo.urllib.request.urlopen")
    def test_http_error_raises_runtime(self, mock_urlopen):
        error = HTTPError("http://x", 400, "Bad", {}, BytesIO(b'{"errors":["bad token"]}'))
        mock_urlopen.side_effect = error
        with self.assertRaises(RuntimeError) as ctx:
            demo.bao_request("sys/wrapping/unwrap", method="POST", data={}, token="dead")
        self.assertIn("400", str(ctx.exception))


class TestWaitForBao(unittest.TestCase):
    """Test wait_for_bao."""

    @patch("demo.urllib.request.urlopen")
    def test_ready_immediately(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        # Should not raise
        demo.wait_for_bao(timeout=2)

    @patch("demo.time.sleep")
    @patch("demo.urllib.request.urlopen")
    def test_timeout_raises(self, mock_urlopen, mock_sleep):
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("conn refused")
        # Patch time to always exceed timeout
        with patch("demo.time.time", side_effect=[0, 0, 100]):
            with self.assertRaises(RuntimeError) as ctx:
                demo.wait_for_bao(timeout=1)
            self.assertIn("did not become ready", str(ctx.exception))


class TestSetupApprole(unittest.TestCase):
    """Test setup_approle configures all components."""

    @patch("demo.bao_request")
    def test_setup_creates_role_id_file(self, mock_req):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            with patch.object(demo, "RUN_DIR", run_dir):
                mock_req.return_value = {"data": {"role_id": "test-role-id"}}
                role_id = demo.setup_approle()
                self.assertEqual(role_id, "test-role-id")
                self.assertEqual((run_dir / "role-id").read_text(), "test-role-id")

    @patch("demo.bao_request")
    def test_setup_handles_already_enabled(self, mock_req):
        """AppRole already enabled should not raise."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            with patch.object(demo, "RUN_DIR", run_dir):
                def side_effect(path, **kwargs):
                    if path == "sys/auth/approle":
                        raise RuntimeError("path is already in use")
                    return {"data": {"role_id": "rid"}}
                mock_req.side_effect = side_effect
                # Should not raise
                demo.setup_approle()


class TestReplayFails(unittest.TestCase):
    """Test test_replay_fails correctly identifies rejection."""

    @patch("demo.bao_request")
    def test_replay_rejected(self, mock_req):
        mock_req.side_effect = RuntimeError("HTTP 400 — bad token")
        # Should not raise (it expects the error)
        demo.test_replay_fails("dead-token-xyz")

    @patch("demo.bao_request")
    def test_replay_unexpected_success_exits(self, mock_req):
        mock_req.return_value = {"data": {"secret_id": "oops"}}
        with self.assertRaises(SystemExit):
            demo.test_replay_fails("should-be-dead")


class TestExpiredTokenFails(unittest.TestCase):
    """Test test_expired_token_fails correctly identifies TTL rejection."""

    @patch("demo.time.sleep")
    @patch("demo.bao_request")
    def test_expired_rejected(self, mock_req, mock_sleep):
        # First call: generate wrap (success). Second call: unwrap (fail).
        mock_req.side_effect = [
            {"wrap_info": {"token": "short-token"}},
            RuntimeError("HTTP 400 — token expired"),
        ]
        # Should not raise
        demo.test_expired_token_fails()
        mock_sleep.assert_called_once_with(3)

    @patch("demo.time.sleep")
    @patch("demo.bao_request")
    def test_expired_unexpected_success_exits(self, mock_req, mock_sleep):
        mock_req.side_effect = [
            {"wrap_info": {"token": "short-token"}},
            {"data": {"secret_id": "oops"}},
        ]
        with self.assertRaises(SystemExit):
            demo.test_expired_token_fails()


if __name__ == "__main__":
    unittest.main()
