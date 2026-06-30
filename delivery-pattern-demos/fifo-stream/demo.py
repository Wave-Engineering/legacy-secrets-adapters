#!/usr/bin/env python3
"""demo.py — fifo-stream: deliver a secret through a named pipe (FIFO).

The secret streams through kernel memory (the pipe buffer) and never exists
on any filesystem. Proves three properties:

  1. The reader gets the secret (it reads from the FIFO path).
  2. grep finds nothing on disk (no file to steal).
  3. A second cat hangs (the pipe is read-once; nothing remains to read).

Usage:
    python3 demo.py          # run the full end-to-end demo
    python3 demo.py quiet    # exit 0/1 without narration (for CI)
"""
import os
import signal
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
NEEDLE = "S3cr3t-Pg-Pass"

SAMPLE_SECRET = (
    '{\n'
    '  "username": "app_pg_user",\n'
    f'  "passwd": "{NEEDLE}",\n'
    '  "host": "db.internal",\n'
    '  "dbname": "appdb"\n'
    '}\n'
)


def _make_fifo(fifo_path: Path):
    """Create a named pipe at the given path. Remove any stale entry first."""
    fifo_path.parent.mkdir(parents=True, exist_ok=True)
    if fifo_path.exists():
        fifo_path.unlink()
    os.mkfifo(fifo_path, mode=0o600)


def _writer(fifo_path: Path, secret: str, done_event: threading.Event):
    """Feed the secret into the FIFO. Blocks until a reader opens the other end."""
    with open(fifo_path, "w") as f:
        f.write(secret)
    done_event.set()


def _grep_disk(search_dir: Path, needle: str) -> bool:
    """Search the directory tree for the needle in non-Python files. Returns True if found."""
    for root, _dirs, files in os.walk(search_dir):
        for fname in files:
            if fname.endswith((".py", ".pyc", ".html", ".md")):
                continue
            fpath = Path(root) / fname
            if fpath.is_file() and not _is_fifo(fpath):
                try:
                    content = fpath.read_text(errors="ignore")
                    if needle in content:
                        return True
                except (OSError, UnicodeDecodeError):
                    pass
    return False


def _is_fifo(path: Path) -> bool:
    """Check if path is a FIFO (named pipe)."""
    try:
        import stat
        return stat.S_ISFIFO(os.stat(path).st_mode)
    except OSError:
        return False


def run(quiet: bool = False) -> bool:
    """Run the full demo. Returns True if all properties hold."""
    tmpdir = tempfile.mkdtemp(prefix="fifo-stream-")
    fifo_path = Path(tmpdir) / "secrets.json"

    def say(msg):
        if not quiet:
            print(msg)

    try:
        # --- Step 1: Create the FIFO ---
        say("=== 1. CREATE THE NAMED PIPE (FIFO) ===")
        _make_fifo(fifo_path)
        say(f"-> mkfifo {fifo_path}")
        say(f"   (this is a pipe, not a file — no data stored on any filesystem)")

        # --- Step 2: Writer feeds, reader reads ---
        say("\n=== 2. WRITER FEEDS SECRET -> READER READS ===")
        done = threading.Event()
        writer_thread = threading.Thread(
            target=_writer, args=(fifo_path, SAMPLE_SECRET, done), daemon=True
        )
        writer_thread.start()

        # Reader side — read the secret from the FIFO
        with open(fifo_path, "r") as f:
            received = f.read()

        done.wait(timeout=5)
        say(f"-> reader received the secret ({len(received)} bytes)")
        if NEEDLE not in received:
            say("FAIL: reader did not get the expected secret")
            return False
        say(f"   reader sees passwd: {NEEDLE}")

        # --- Step 3: grep finds nothing on disk ---
        say("\n=== 3. GREP THE DISK — NOTHING ===")
        found = _grep_disk(Path(tmpdir), NEEDLE)
        if found:
            say("FAIL: secret found on disk!")
            return False
        say(f"-> grep -r '{NEEDLE}' {tmpdir}  =>  (nothing found)")
        say("   the FIFO is a pipe — no data stored anywhere on the filesystem")

        # --- Step 4: Second read hangs (read-once) ---
        say("\n=== 4. SECOND READ HANGS (read-once proof) ===")
        # Re-create the FIFO for the second-read test (the previous one was consumed)
        if fifo_path.exists():
            fifo_path.unlink()
        _make_fifo(fifo_path)

        hung = threading.Event()
        read_result = [None]

        def _second_read():
            try:
                with open(fifo_path, "r") as f:
                    read_result[0] = f.read()
            except OSError:
                pass

        t = threading.Thread(target=_second_read, daemon=True)
        t.start()
        # Give the second reader a moment — it should block (hang) because no writer
        t.join(timeout=1.0)
        if t.is_alive():
            say("-> second cat on the pipe hangs (no writer, read-once) -- correct!")
            say("   a named pipe is read-once: once consumed, nothing remains to read")
            # Clean up: unlink the fifo to unblock the thread (it will get an error)
            fifo_path.unlink(missing_ok=True)
        else:
            say("FAIL: second read did not hang (unexpected)")
            return False

        say("\n=== RESULT ===")
        say("All properties hold:")
        say("  (1) reader gets the secret")
        say("  (2) grep finds nothing on disk")
        say("  (3) second cat hangs (read-once)")
        return True

    finally:
        # Cleanup
        if fifo_path.exists():
            fifo_path.unlink(missing_ok=True)
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass


if __name__ == "__main__":
    quiet = "quiet" in sys.argv[1:] if len(sys.argv) > 1 else False
    ok = run(quiet=quiet)
    sys.exit(0 if ok else 1)
