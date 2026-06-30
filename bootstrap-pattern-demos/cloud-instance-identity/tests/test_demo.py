"""Tests for demo.py — integration test (requires Docker for full run)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestDemoImports:
    """Verify demo.py can be imported without side effects."""

    def test_imports_cleanly(self):
        """demo.py should import without starting servers or Docker."""
        import demo  # noqa: F401
        assert hasattr(demo, "main")
        assert hasattr(demo, "_start_mock_metadata")
        assert hasattr(demo, "_setup_openbao")

    def test_has_all_proof_functions(self):
        """demo.py should define the key orchestration functions."""
        import demo  # noqa: F401
        assert callable(demo._start_docker)
        assert callable(demo._stop_docker)
        assert callable(demo._cleanup)
        assert callable(demo._wait_for_bao)
        assert callable(demo._install_mock_auth)


class TestDemoConfiguration:
    """Verify demo.py configuration constants."""

    def test_uses_fake_secret(self):
        """The canonical fake secret should be S3cr3t-Pg-Pass."""
        import demo  # noqa: F401
        assert demo.SECRET_VALUE == "S3cr3t-Pg-Pass"

    def test_uses_dev_token(self):
        """Bootstrap token should be the obvious dev value."""
        import demo  # noqa: F401
        assert demo.BAO_TOKEN == "dev-only-root-token"

    def test_output_path_in_run_dir(self):
        """Output file should be in the gitignored run/ directory."""
        import demo  # noqa: F401
        assert "run" in str(demo.OUTPUT_FILE)
        assert demo.OUTPUT_FILE.name == "secret.json"
