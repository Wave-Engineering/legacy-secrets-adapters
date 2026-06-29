"""Unit tests for broker.py — template rendering and file output.

These tests exercise the broker's core logic WITHOUT needing Docker or OpenBao.
They mock the vault API responses and verify:
  - Template rendering with Jinja2
  - File writing with correct permissions
  - Rotation detection (version change)
  - Error handling on unreachable vault
"""
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add pattern dir to path so we can import broker
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import broker  # noqa: E402


def _mock_kv_response(data: dict, version: int = 1) -> dict:
    """Build a mock KV v2 API response."""
    return {
        "data": {
            "data": data,
            "metadata": {"version": version}
        }
    }


class TestRenderTemplate:
    """Test Jinja2 template rendering."""

    def test_renders_db_conf(self, tmp_path):
        """The db.conf.j2 template renders with secret data."""
        template = tmp_path / "db.conf.j2"
        template.write_text(
            "[database]\n"
            "host = {{ host }}\n"
            "port = {{ port }}\n"
            "password = {{ password }}\n"
        )
        with patch.object(broker, "TEMPLATE_PATH", template):
            result = broker.render_template({
                "host": "127.0.0.1",
                "port": "5432",
                "password": "S3cr3t-Pg-Pass",
            })
        assert "host = 127.0.0.1" in result
        assert "port = 5432" in result
        assert "password = S3cr3t-Pg-Pass" in result

    def test_strict_undefined_raises(self, tmp_path):
        """Missing template variables raise an error (strict mode)."""
        template = tmp_path / "test.j2"
        template.write_text("{{ missing_var }}")
        with patch.object(broker, "TEMPLATE_PATH", template):
            try:
                broker.render_template({})
                assert False, "Should have raised"
            except Exception:
                pass  # Expected: jinja2.UndefinedError


class TestWriteOutput:
    """Test file writing with permissions."""

    def test_writes_content(self, tmp_path):
        """Output file contains the rendered content."""
        output = tmp_path / "run" / "db.conf"
        with patch.object(broker, "OUTPUT_PATH", output):
            broker.write_output("test content\n")
        assert output.read_text() == "test content\n"

    def test_creates_parent_dirs(self, tmp_path):
        """Parent directories are created if missing."""
        output = tmp_path / "deep" / "nested" / "file.conf"
        with patch.object(broker, "OUTPUT_PATH", output):
            broker.write_output("data")
        assert output.exists()

    def test_file_permissions(self, tmp_path):
        """Output file has 0600 permissions (owner read/write only)."""
        output = tmp_path / "secret.conf"
        with patch.object(broker, "OUTPUT_PATH", output):
            broker.write_output("secret data")
        mode = stat.S_IMODE(os.stat(output).st_mode)
        assert mode == 0o600


class TestFetchSecret:
    """Test vault API interaction."""

    def test_fetch_returns_data_and_version(self):
        """fetch_secret() returns (data_dict, version_int)."""
        mock_response = _mock_kv_response(
            {"username": "app", "password": "S3cr3t-Pg-Pass"}, version=3
        )
        with patch.object(broker, "_bao_request", return_value=mock_response):
            data, version = broker.fetch_secret()
        assert data == {"username": "app", "password": "S3cr3t-Pg-Pass"}
        assert version == 3

    def test_fetch_error_propagates(self):
        """Network errors from _bao_request propagate as RuntimeError."""
        with patch.object(broker, "_bao_request", side_effect=RuntimeError("connection refused")):
            try:
                broker.fetch_secret()
                assert False, "Should have raised"
            except RuntimeError as e:
                assert "connection refused" in str(e)


class TestFetchAndRender:
    """Test the combined fetch + render + write pipeline."""

    def test_end_to_end(self, tmp_path):
        """fetch_and_render writes correct content from mocked vault response."""
        template = tmp_path / "tmpl.j2"
        template.write_text("user={{ username }}\npass={{ password }}\n")
        output = tmp_path / "out.conf"

        mock_response = _mock_kv_response(
            {"username": "app_pg_user", "password": "S3cr3t-Pg-Pass"}, version=1
        )

        with patch.object(broker, "TEMPLATE_PATH", template), \
             patch.object(broker, "OUTPUT_PATH", output), \
             patch.object(broker, "_bao_request", return_value=mock_response):
            version = broker.fetch_and_render()

        assert version == 1
        content = output.read_text()
        assert "user=app_pg_user" in content
        assert "pass=S3cr3t-Pg-Pass" in content

    def test_rotation_changes_version(self, tmp_path):
        """Successive calls with different versions return different version numbers."""
        template = tmp_path / "tmpl.j2"
        template.write_text("p={{ password }}\n")
        output = tmp_path / "out.conf"

        v1_resp = _mock_kv_response({"password": "S3cr3t-Pg-Pass"}, version=1)
        v2_resp = _mock_kv_response({"password": "R0tated-Pg-Pass-v2"}, version=2)

        with patch.object(broker, "TEMPLATE_PATH", template), \
             patch.object(broker, "OUTPUT_PATH", output):
            with patch.object(broker, "_bao_request", return_value=v1_resp):
                ver1 = broker.fetch_and_render()
            with patch.object(broker, "_bao_request", return_value=v2_resp):
                ver2 = broker.fetch_and_render()

        assert ver1 == 1
        assert ver2 == 2
        assert "R0tated-Pg-Pass-v2" in output.read_text()


class TestRunOnce:
    """Test single-shot mode."""

    def test_run_once_calls_fetch_and_render(self, tmp_path):
        """run_once() completes without error when mocked."""
        template = tmp_path / "t.j2"
        template.write_text("x={{ password }}\n")
        output = tmp_path / "o.conf"
        mock_resp = _mock_kv_response({"password": "test"}, version=1)

        with patch.object(broker, "TEMPLATE_PATH", template), \
             patch.object(broker, "OUTPUT_PATH", output), \
             patch.object(broker, "_bao_request", return_value=mock_resp):
            broker.run_once()

        assert output.exists()


class TestLegacyReader:
    """Test legacy_reader.py reads the rendered config correctly."""

    def test_reader_parses_ini(self, tmp_path):
        """The legacy reader parses a rendered INI config."""
        config = tmp_path / "db.conf"
        config.write_text(
            "[database]\n"
            "host = 127.0.0.1\n"
            "port = 5432\n"
            "dbname = appdb\n"
            "username = app_pg_user\n"
            "password = S3cr3t-Pg-Pass\n"
        )
        import subprocess
        reader = Path(__file__).resolve().parent.parent / "legacy_reader.py"
        env = {**os.environ, "CONFIG_PATH": str(config)}
        r = subprocess.run([sys.executable, str(reader)], env=env,
                           capture_output=True, text=True)
        assert r.returncode == 0
        assert "app_pg_user" in r.stdout
        assert "S3cr3t-Pg-Pass" in r.stdout

    def test_reader_fails_on_missing_file(self, tmp_path):
        """The legacy reader exits non-zero if config file is missing."""
        import subprocess
        reader = Path(__file__).resolve().parent.parent / "legacy_reader.py"
        env = {**os.environ, "CONFIG_PATH": str(tmp_path / "nonexistent.conf")}
        r = subprocess.run([sys.executable, str(reader)], env=env,
                           capture_output=True, text=True)
        assert r.returncode != 0
        assert "FATAL" in r.stderr


class TestDemoOrchestration:
    """Test demo.py helper functions."""

    def test_seed_secret_format(self):
        """The demo's secret dictionaries have the expected shape."""
        # Import demo module
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import demo  # noqa: E402
        for secret in [demo.INITIAL_SECRET, demo.ROTATED_SECRET]:
            assert "host" in secret
            assert "port" in secret
            assert "dbname" in secret
            assert "username" in secret
            assert "password" in secret
        assert demo.INITIAL_SECRET["password"] == "S3cr3t-Pg-Pass"
        assert demo.ROTATED_SECRET["password"] == "R0tated-Pg-Pass-v2"
