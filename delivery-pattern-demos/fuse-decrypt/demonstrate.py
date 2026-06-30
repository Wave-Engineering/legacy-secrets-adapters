#!/usr/bin/env python3
"""demonstrate.py — an INTERACTIVE experience of fuse-decrypt: a FUSE filesystem
that decrypts on read and encrypts on write, making arbitrary POSIX I/O transparent.

    ./demonstrate.py

Requires: /dev/fuse, pyfuse3, cryptography.
If /dev/fuse is absent, prints a pointer to deck.html and exits gracefully.
"""
import json
import multiprocessing
import os
import shutil
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
WRITEUP = HERE / "enlighten.html"

SAMPLE = {
    "username": "app_pg_user",
    "passwd": NEEDLE,
    "host": "db.internal",
    "dbname": "appdb",
}

# --- Pretty printing ----------------------------------------------------------
TTY = sys.stdout.isatty()
def _c(code, s): return f"\033[{code}m{s}\033[0m" if TTY else s
def GREEN(s): return _c("1;32", s)
def RED(s):   return _c("1;31", s)
def DIM(s):   return _c("2", s)
def BOLD(s):  return _c("1", s)
def CYAN(s):  return _c("36", s)


def clear_screen():
    if TTY:
        print("\033[H\033[2J\033[3J", end="", flush=True)


def coach(text):
    print("\n    " + DIM(text.replace("\n", "\n    ")))


def verdict(text, ok=True):
    print("\n    " + (GREEN if ok else RED)(text))


def pause(prompt="Press [enter] to continue ..."):
    print("\n    " + DIM(prompt), end="", flush=True)
    try:
        input()
    except EOFError:
        raise SystemExit(0)


# --- FUSE mount management ----------------------------------------------------
_mount_proc: multiprocessing.Process | None = None


def _fuse_available() -> bool:
    return os.path.exists("/dev/fuse") and os.access("/dev/fuse", os.R_OK | os.W_OK)


def _mount_target(source_dir: Path, mount_point: Path, key: bytes):
    """Target for the FUSE mount subprocess."""
    import pyfuse3
    import trio
    mount_point.mkdir(parents=True, exist_ok=True)
    ops = fusefs.DecryptFS(source_dir, key)
    fuse_options = set(pyfuse3.default_options)
    fuse_options.add("fsname=fuse-decrypt")
    fuse_options.discard("default_permissions")
    pyfuse3.init(ops, str(mount_point), fuse_options)
    try:
        trio.run(pyfuse3.main)
    except:
        pass
    finally:
        try:
            pyfuse3.close(unmount=False)
        except:
            pass


def mount(key: bytes) -> bool:
    """Mount the FUSE filesystem. Returns True on success."""
    global _mount_proc
    if _mount_proc and _mount_proc.is_alive():
        return True
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    MOUNT_POINT.mkdir(parents=True, exist_ok=True)
    _mount_proc = multiprocessing.Process(target=_mount_target,
                                          args=(SOURCE_DIR, MOUNT_POINT, key),
                                          daemon=True)
    _mount_proc.start()
    for _ in range(50):
        if os.path.ismount(str(MOUNT_POINT)):
            return True
        time.sleep(0.1)
    return False


def unmount():
    """Unmount the FUSE filesystem."""
    global _mount_proc
    for cmd in ("fusermount3", "fusermount"):
        r = subprocess.run([cmd, "-u", str(MOUNT_POINT)],
                          capture_output=True, timeout=5)
        if r.returncode == 0:
            break
    if _mount_proc:
        _mount_proc.join(timeout=5)
        if _mount_proc.is_alive():
            _mount_proc.kill()
        _mount_proc = None


def is_mounted() -> bool:
    return os.path.ismount(str(MOUNT_POINT))


# --- Demo actions -------------------------------------------------------------
def setup_cipherstore(key: bytes):
    """Create the ciphertext backing store."""
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    plaintext = (json.dumps(SAMPLE, indent=2) + "\n").encode()
    ct = fusefs.encrypt_blob(key, plaintext)
    (SOURCE_DIR / SECRET_FILE_NAME).write_bytes(ct)


def act_mount(key: bytes):
    """Mount the FUSE filesystem."""
    if is_mounted():
        print(GREEN("    FUSE filesystem is already mounted."))
        return
    coach("Mounting the decrypt-on-read filesystem...\n"
          "Ciphertext on disk -> plaintext view at the mount point.")
    ok = mount(key)
    if ok:
        print(GREEN("    MOUNTED: cipherstore/ -> mnt/ (AES-256-GCM decrypt-on-read)"))
    else:
        print(RED("    FAILED to mount. Check /dev/fuse and pyfuse3."))


def act_unmount():
    """Unmount the FUSE filesystem."""
    if not is_mounted():
        print(DIM("    FUSE filesystem is not mounted."))
        return
    unmount()
    time.sleep(0.3)
    print(RED("    UNMOUNTED: the plaintext view is gone. Disk holds only ciphertext."))


def act_read_through_mount():
    """Read the secret through the FUSE mount."""
    mt_file = MOUNT_POINT / SECRET_FILE_NAME
    if not is_mounted():
        coach("The FUSE filesystem is not mounted. The reader will fail.")
        print(RED(f"    {mt_file} does not exist (mount is down)"))
        verdict("No mount, no service.", ok=False)
        return
    coach("The legacy reader opens its config through the FUSE mount.\n"
          "It has no idea the file is decrypted on the fly from ciphertext.")
    r = subprocess.run(
        [sys.executable, str(HERE / "legacy_reader.py"), "--config", str(mt_file)],
        capture_output=True, text=True, timeout=10
    )
    if r.stdout:
        print()
        for line in r.stdout.rstrip().split("\n"):
            print(f"    {line}")
    if r.returncode != 0:
        verdict("Reader FAILED (see above).", ok=False)
    else:
        verdict("Reader connected. Seek + write-back exercised. Nothing on disk changed.", ok=True)


def act_detect():
    """Hunt the disk for plaintext."""
    coach(f"Searching the cipherstore for the password '{NEEDLE}'...")
    ct_file = SOURCE_DIR / SECRET_FILE_NAME
    if ct_file.exists():
        data = ct_file.read_bytes()
        found = NEEDLE.encode() in data
        if found:
            print(RED(f"    FOUND '{NEEDLE}' in {ct_file.name} — plaintext on disk!"))
            verdict("LEAK: plaintext found on disk.", ok=False)
        else:
            print(DIM(f"    grep '{NEEDLE}' cipherstore/{ct_file.name} -> (not found)"))
            coach("The file is pure ciphertext. Only through the FUSE mount is it readable.")
            verdict("Ciphertext only on disk. The FUSE layer is the sole gate to plaintext.", ok=True)
    else:
        print(DIM("    (no cipherstore files yet — mount first)"))


def act_hexdump():
    """Show a hex dump of the ciphertext file."""
    ct_file = SOURCE_DIR / SECRET_FILE_NAME
    if not ct_file.exists():
        print(DIM("    (no cipherstore yet)"))
        return
    coach("The raw bytes on disk — pure ciphertext (nonce + AES-256-GCM output):")
    data = ct_file.read_bytes()
    # Show first 128 bytes as hex
    hex_lines = []
    for i in range(0, min(len(data), 128), 16):
        chunk = data[i:i+16]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        hex_lines.append(f"    {i:04x}  {hex_part:<48s}  {ascii_part}")
    print()
    for line in hex_lines:
        print(line)
    if len(data) > 128:
        print(f"    ... ({len(data)} bytes total)")


def act_enlighten():
    """Open the concept page in a browser."""
    if not WRITEUP.exists():
        print(DIM(f"    write-up not found at {WRITEUP}"))
        return
    for opener in ("xdg-open", "sensible-browser", "open"):
        if shutil.which(opener):
            subprocess.run([opener, str(WRITEUP)],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(DIM(f"    opened {WRITEUP.name} in your browser"))
            return
    print(DIM(f"    no GUI opener found — open this yourself: file://{WRITEUP}"))


# --- Menu ---------------------------------------------------------------------
def menu(mounted: bool):
    state = GREEN("MOUNTED") if mounted else RED("UNMOUNTED")
    print("\n" + BOLD("════ fuse-decrypt — a transparent decrypt-on-read filesystem ════"))
    print(f"     FUSE mount: {state}")
    print()
    print("  0) Enlighten me                " + DIM("(open the concept page)"))
    print("  1) Mount the FUSE filesystem   " + DIM("(ciphertext -> plaintext view)"))
    print("  2) Unmount                     " + DIM("(plaintext view disappears)"))
    print("  3) Run the legacy reader       " + DIM("(seek + write-back through mount)"))
    print("  4) Detect plaintext on disk    " + DIM("(grep the cipherstore)"))
    print("  5) Hexdump backing file        " + DIM("(see the raw ciphertext)"))
    print("  6) Exit")
    print()


def main():
    if not _fuse_available():
        print("fuse-decrypt: /dev/fuse not available (no FUSE support in this environment)")
        print(f"  -> open {HERE / 'deck.html'} in a browser for the recorded walkthrough")
        sys.exit(0)

    os.chdir(HERE)

    # Setup
    key = fusefs.generate_key()
    KEY_FILE.write_text(key.hex())
    setup_cipherstore(key)

    try:
        while True:
            clear_screen()
            menu(is_mounted())
            print("  Select: ", end="", flush=True)
            try:
                choice = input().strip()
            except EOFError:
                break
            if choice == "6":
                print(DIM("\n  Done."))
                break
            elif choice == "0":
                act_enlighten()
            elif choice == "1":
                act_mount(key)
            elif choice == "2":
                act_unmount()
            elif choice == "3":
                act_read_through_mount()
            elif choice == "4":
                act_detect()
            elif choice == "5":
                act_hexdump()
            else:
                continue
            pause()
    finally:
        if is_mounted():
            unmount()
        # Cleanup runtime artifacts
        if SOURCE_DIR.exists():
            shutil.rmtree(SOURCE_DIR, ignore_errors=True)
        KEY_FILE.unlink(missing_ok=True)
        if MOUNT_POINT.exists():
            try:
                MOUNT_POINT.rmdir()
            except OSError:
                pass


if __name__ == "__main__":
    main()
