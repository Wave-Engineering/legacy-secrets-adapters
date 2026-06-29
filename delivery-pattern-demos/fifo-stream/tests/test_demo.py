"""Unit tests for the fifo-stream demo logic."""
import os
import stat
import tempfile
import threading
import time
from pathlib import Path
from unittest import TestCase

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import demo  # noqa: E402


class TestMakeFifo(TestCase):
    """Test FIFO creation."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="fifo-test-")
        self.fifo_path = Path(self.tmpdir) / "test.fifo"

    def tearDown(self):
        if self.fifo_path.exists():
            self.fifo_path.unlink()
        os.rmdir(self.tmpdir)

    def test_creates_fifo(self):
        demo._make_fifo(self.fifo_path)
        self.assertTrue(self.fifo_path.exists())
        self.assertTrue(stat.S_ISFIFO(os.stat(self.fifo_path).st_mode))

    def test_fifo_mode(self):
        demo._make_fifo(self.fifo_path)
        mode = os.stat(self.fifo_path).st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_replaces_stale_fifo(self):
        # Create a regular file first
        self.fifo_path.write_text("stale")
        demo._make_fifo(self.fifo_path)
        self.assertTrue(stat.S_ISFIFO(os.stat(self.fifo_path).st_mode))

    def test_creates_parent_dirs(self):
        nested = Path(self.tmpdir) / "sub" / "dir" / "test.fifo"
        demo._make_fifo(nested)
        self.assertTrue(stat.S_ISFIFO(os.stat(nested).st_mode))
        # cleanup
        nested.unlink()
        nested.parent.rmdir()
        nested.parent.parent.rmdir()


class TestWriter(TestCase):
    """Test the writer thread."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="fifo-test-")
        self.fifo_path = Path(self.tmpdir) / "test.fifo"
        demo._make_fifo(self.fifo_path)

    def tearDown(self):
        if self.fifo_path.exists():
            self.fifo_path.unlink()
        os.rmdir(self.tmpdir)

    def test_writer_delivers_secret(self):
        done = threading.Event()
        secret = "hello-secret"
        t = threading.Thread(target=demo._writer, args=(self.fifo_path, secret, done), daemon=True)
        t.start()

        # Reader side
        with open(self.fifo_path, "r") as f:
            received = f.read()

        done.wait(timeout=5)
        self.assertEqual(received, secret)
        self.assertTrue(done.is_set())


class TestGrepDisk(TestCase):
    """Test grep-disk function."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="fifo-test-")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_finds_nothing_in_empty_dir(self):
        self.assertFalse(demo._grep_disk(Path(self.tmpdir), "needle"))

    def test_finds_nothing_when_only_fifo(self):
        fifo = Path(self.tmpdir) / "secrets.json"
        os.mkfifo(fifo, mode=0o600)
        self.assertFalse(demo._grep_disk(Path(self.tmpdir), demo.NEEDLE))

    def test_finds_secret_in_regular_file(self):
        target = Path(self.tmpdir) / "leaked.txt"
        target.write_text(f"password is {demo.NEEDLE}")
        self.assertTrue(demo._grep_disk(Path(self.tmpdir), demo.NEEDLE))

    def test_skips_python_files(self):
        target = Path(self.tmpdir) / "code.py"
        target.write_text(f"NEEDLE = '{demo.NEEDLE}'")
        self.assertFalse(demo._grep_disk(Path(self.tmpdir), demo.NEEDLE))


class TestIsFifo(TestCase):
    """Test the is_fifo helper."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="fifo-test-")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_regular_file(self):
        f = Path(self.tmpdir) / "regular.txt"
        f.write_text("hello")
        self.assertFalse(demo._is_fifo(f))

    def test_fifo(self):
        f = Path(self.tmpdir) / "pipe"
        os.mkfifo(f)
        self.assertTrue(demo._is_fifo(f))

    def test_nonexistent(self):
        f = Path(self.tmpdir) / "nope"
        self.assertFalse(demo._is_fifo(f))


class TestRunEndToEnd(TestCase):
    """Integration test: run() should return True (all properties hold)."""

    def test_run_succeeds(self):
        self.assertTrue(demo.run(quiet=True))


if __name__ == "__main__":
    import unittest
    unittest.main()
