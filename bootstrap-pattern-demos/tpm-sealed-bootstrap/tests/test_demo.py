"""Tests for demo.py — the end-to-end orchestrator."""
import os
import shutil
import sys
from pathlib import Path
from unittest import mock

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import demo  # noqa: E402


class TestPreflight:
    """Test the preflight() check."""

    def test_missing_systemd_creds(self):
        """Returns False when systemd-creds is not found."""
        with mock.patch("shutil.which", side_effect=lambda x: None if x == "systemd-creds" else "/usr/bin/swtpm"):
            assert demo.preflight() is False

    def test_missing_swtpm(self):
        """Returns False when swtpm is not found."""
        with mock.patch("shutil.which", side_effect=lambda x: None if x == "swtpm" else "/usr/bin/systemd-creds"):
            # Also need to mock the version check
            with mock.patch("subprocess.run") as mock_run:
                mock_run.return_value = mock.MagicMock(returncode=0, stdout="systemd 255 (255-1)\n")
                assert demo.preflight() is False

    def test_old_systemd_version(self):
        """Returns False when systemd version < 250."""
        def which_mock(x):
            return f"/usr/bin/{x}" if x in ("systemd-creds", "swtpm") else None

        with mock.patch("shutil.which", side_effect=which_mock):
            with mock.patch("subprocess.run") as mock_run:
                mock_run.return_value = mock.MagicMock(returncode=0, stdout="systemd 249 (249-1)\n")
                assert demo.preflight() is False

    def test_sufficient_systemd_version(self):
        """Returns True when systemd >= 250 and swtpm present."""
        def which_mock(x):
            return f"/usr/bin/{x}" if x in ("systemd-creds", "swtpm") else None

        with mock.patch("shutil.which", side_effect=which_mock):
            with mock.patch("subprocess.run") as mock_run:
                mock_run.return_value = mock.MagicMock(returncode=0, stdout="systemd 256 (256-1)\n")
                assert demo.preflight() is True


class TestStepOpaque:
    """Test that step_opaque correctly identifies the sealed blob is opaque."""

    def test_plaintext_not_in_blob(self, tmp_path):
        """Passes when plaintext is not in the sealed blob."""
        sealed = tmp_path / "test.cred"
        sealed.write_bytes(b"\x00\x01\x02\x03encrypted-gibberish-here")
        # Should not raise
        demo.step_opaque(sealed)

    def test_plaintext_in_blob_fails(self, tmp_path):
        """Exits when plaintext IS found in the blob."""
        sealed = tmp_path / "test.cred"
        sealed.write_bytes(b"header" + demo.FAKE_SECRET.encode() + b"trailer")
        with pytest.raises(SystemExit):
            demo.step_opaque(sealed)


class TestConstants:
    """Verify demo constants match spec requirements."""

    def test_fake_secret_value(self):
        """The fake secret is the spec-required obvious dev value."""
        assert demo.FAKE_SECRET == "S3cr3t-Pg-Pass"

    def test_cred_name(self):
        """Credential name matches the systemd service expectation."""
        assert demo.CRED_NAME == "bao-token"

    def test_deck_path_exists(self):
        """deck.html path is correctly computed."""
        assert demo.DECK == HERE / "deck.html"
