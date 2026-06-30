#!/usr/bin/env python3
"""demo.py — end-to-end orchestration of the fuse-decrypt pattern.

Proves:
  1. The backing file on disk is ciphertext (not human-readable)
  2. The legacy reader sees plaintext through the FUSE mount
  3. A write-back through the mount produces ciphertext on disk
  4. Unmount -> remount round-trip works (data persists as ciphertext)

Requires: /dev/fuse, pyfuse3, cryptography.

If /dev/fuse is absent, prints a helpful message and exits 0 with a pointer to deck.html.
"""
import json
import multiprocessing
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fusefs  # noqa: E402

# --- Configuration ---
NEEDLE = "S3cr3t-Pg-Pass"
SOURCE_DIR = HERE / "cipherstore"
MOUNT_POINT = HERE / "mnt"
KEY_FILE = HERE / "demo.key"
SECRET_FILE_NAME = "secrets.json"

SAMPLE = {
    "username": "app_pg_user",
    "passwd": NEEDLE,
    "host": "db.internal",
    "dbname": "appdb",
}


def _fuse_available() -> bool:
    return os.path.exists("/dev/fuse") and os.access("/dev/fuse", os.R_OK | os.W_OK)


def _cleanup():
    """Unmount and remove runtime artifacts."""
    # Try fusermount3 first, then fusermount
    for cmd in ("fusermount3", "fusermount"):
        r = subprocess.run([cmd, "-u", str(MOUNT_POINT)],
                          capture_output=True, timeout=5)
        if r.returncode == 0:
            break
    # Clean up directories
    if MOUNT_POINT.exists():
        try:
            MOUNT_POINT.rmdir()
        except OSError:
            pass


def _setup() -> bytes:
    """Create key, source dir, and encrypt the sample secret. Returns the key."""
    _cleanup()
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    MOUNT_POINT.mkdir(parents=True, exist_ok=True)

    key = fusefs.generate_key()
    KEY_FILE.write_text(key.hex())

    # Encrypt the sample config
    plaintext = (json.dumps(SAMPLE, indent=2) + "\n").encode()
    ct = fusefs.encrypt_blob(key, plaintext)
    (SOURCE_DIR / SECRET_FILE_NAME).write_bytes(ct)

    return key


def _mount_process(source_dir: Path, mount_point: Path, key: bytes):
    """Target for the FUSE mount subprocess."""
    import pyfuse3 as _pyfuse3
    import trio as _trio
    mount_point.mkdir(parents=True, exist_ok=True)
    ops = fusefs.DecryptFS(source_dir, key)
    fuse_options = set(_pyfuse3.default_options)
    fuse_options.add("fsname=fuse-decrypt")
    fuse_options.discard("default_permissions")
    _pyfuse3.init(ops, str(mount_point), fuse_options)
    try:
        _trio.run(_pyfuse3.main)
    except:
        pass
    finally:
        try:
            _pyfuse3.close(unmount=False)
        except:
            pass


def _start_mount(key: bytes) -> multiprocessing.Process:
    """Start the FUSE daemon in a subprocess."""
    p = multiprocessing.Process(target=_mount_process,
                                args=(SOURCE_DIR, MOUNT_POINT, key),
                                daemon=True)
    p.start()
    # Wait for mount to appear
    for _ in range(50):
        if os.path.ismount(str(MOUNT_POINT)):
            return p
        time.sleep(0.1)
    raise RuntimeError("FUSE mount did not appear within 5 seconds")


def _unmount():
    """Unmount the FUSE filesystem."""
    for cmd in ("fusermount3", "fusermount"):
        r = subprocess.run([cmd, "-u", str(MOUNT_POINT)],
                          capture_output=True, timeout=5)
        if r.returncode == 0:
            return
    raise RuntimeError("failed to unmount")


def _is_ciphertext(path: Path) -> bool:
    """Check that a file does NOT contain the plaintext needle."""
    try:
        data = path.read_bytes()
        return NEEDLE.encode() not in data
    except Exception:
        return False


def main():
    if not _fuse_available():
        print("fuse-decrypt: /dev/fuse not available (no FUSE support in this environment)")
        print(f"  -> open {HERE / 'deck.html'} in a browser for the recorded walkthrough")
        sys.exit(0)

    proc = None
    try:
        print("=== fuse-decrypt: end-to-end demo ===")
        print()

        # --- Setup ---
        key = _setup()
        ct_file = SOURCE_DIR / SECRET_FILE_NAME
        mt_file = MOUNT_POINT / SECRET_FILE_NAME

        # --- 1. Backing file is ciphertext ---
        print("1. Backing file is ciphertext:")
        assert _is_ciphertext(ct_file), "FAIL: backing file contains plaintext!"
        print(f"   grep '{NEEDLE}' {ct_file.name} -> NOT FOUND (ciphertext confirmed)")
        print()

        # --- 2. Mount and read through FUSE ---
        print("2. Mount FUSE filesystem and read through it:")
        proc = _start_mount(key)
        assert mt_file.exists(), f"FAIL: {mt_file} not visible through mount"
        content = mt_file.read_text()
        cfg = json.loads(content)
        assert cfg["passwd"] == NEEDLE, "FAIL: plaintext not visible through mount!"
        print(f"   mounted {SOURCE_DIR.name}/ -> {MOUNT_POINT.name}/")
        print(f"   read {mt_file.name} through mount: passwd={cfg['passwd'][:4]}... (plaintext!)")
        print()

        # --- 3. Write-back through mount produces ciphertext on disk ---
        print("3. Write-back through mount:")
        cfg["last_access"] = "2026-01-01T09:00:00Z"
        mt_file.write_text(json.dumps(cfg, indent=2) + "\n")
        # Give FUSE a moment to flush
        time.sleep(0.2)
        # Verify the on-disk file is still ciphertext
        assert _is_ciphertext(ct_file), "FAIL: backing file became plaintext after write!"
        print(f"   wrote last_access through mount")
        print(f"   backing file on disk: still ciphertext (no plaintext leaked)")
        print()

        # --- 4. Unmount -> remount round-trip ---
        print("4. Unmount -> remount round-trip:")
        _unmount()
        proc.join(timeout=5)
        proc = None
        time.sleep(0.3)

        # Remount
        proc = _start_mount(key)
        content = mt_file.read_text()
        cfg2 = json.loads(content)
        assert cfg2["passwd"] == NEEDLE, "FAIL: password not readable after remount!"
        assert cfg2["last_access"] == "2026-01-01T09:00:00Z", "FAIL: write-back lost on remount!"
        print(f"   unmounted, remounted")
        print(f"   re-read: passwd={cfg2['passwd'][:4]}..., last_access={cfg2['last_access']}")
        print(f"   round-trip confirmed!")
        print()

        # --- 5. Run the legacy reader ---
        print("5. Legacy reader with seek + write-back:")
        r = subprocess.run(
            [sys.executable, str(HERE / "legacy_reader.py"),
             "--config", str(mt_file)],
            capture_output=True, text=True, timeout=10
        )
        print(r.stdout.rstrip())
        if r.returncode != 0:
            print(f"   FAIL: legacy_reader.py exited {r.returncode}", file=sys.stderr)
            if r.stderr:
                print(r.stderr, file=sys.stderr)
            sys.exit(1)
        print()

        # Final verification: disk still ciphertext
        assert _is_ciphertext(ct_file), "FAIL: backing file is plaintext at end!"

        print("=== PASS: all fuse-decrypt properties verified ===")

    finally:
        # Cleanup
        if proc and proc.is_alive():
            _unmount()
            proc.join(timeout=5)
            if proc.is_alive():
                proc.kill()
        _cleanup()
        # Remove runtime artifacts
        if SOURCE_DIR.exists():
            import shutil
            shutil.rmtree(SOURCE_DIR, ignore_errors=True)
        KEY_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
