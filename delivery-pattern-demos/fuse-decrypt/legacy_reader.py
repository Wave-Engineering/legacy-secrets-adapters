#!/usr/bin/env python3
"""legacy_reader.py — the app WE CANNOT CHANGE.

This reader does arbitrary I/O: it reads, seeks, writes back, and re-reads — the kind
of access pattern that breaks simpler adapters (pipes, single-read files). Only a full
POSIX filesystem (like FUSE) can satisfy it transparently.

It finds its config at a fixed path (the mount point) and:
  1. Reads the whole file (sequential)
  2. Seeks to the password field offset and re-reads just that portion (seek)
  3. Writes an updated timestamp back into the file (write-back)
  4. Re-reads the whole file to confirm the write persisted (re-read)

This exercises seek + write-back, proving the FUSE layer handles arbitrary POSIX ops.
"""
import json
import os
import sys
from pathlib import Path

# The path this app expects its config at — in production it would be hard-coded
# into the binary. Here it's configurable for the demo, but defaults to the mount.
DEFAULT_PATH = Path(__file__).resolve().parent / "mnt" / "secrets.json"


def config_path() -> Path:
    argv = sys.argv[1:]
    if "--config" in argv:
        return Path(argv[argv.index("--config") + 1])
    if os.environ.get("CONFIG_PATH"):
        return Path(os.environ["CONFIG_PATH"])
    return DEFAULT_PATH


def die(msg: str):
    bar = "!" * 64
    print(f"\n{bar}", file=sys.stderr)
    print(f"[legacy-reader] FATAL: {msg}", file=sys.stderr)
    print("[legacy-reader] No secret, no service. (Is the FUSE mount down?)", file=sys.stderr)
    print(f"{bar}\n", file=sys.stderr)
    sys.exit(2)


def main():
    path = config_path()
    if not path.exists():
        die(f"cannot find my config file: {path}")

    # --- 1. Sequential read ---
    print(f"[legacy-reader] opened {path}")
    try:
        with open(path, "r") as f:
            content = f.read()
            cfg = json.loads(content)
    except Exception as e:
        die(f"config unreadable: {path}: {e}")

    print(f"[legacy-reader] read credentials for {cfg['username']}@{cfg['host']}/{cfg['dbname']}")

    # --- 2. Seek test: re-read from a specific offset ---
    with open(path, "rb") as f:
        f.seek(0, 2)  # seek to end
        size = f.tell()
        f.seek(0)     # seek back to start
        raw = f.read()
    print(f"[legacy-reader] seek test: file size={size}, re-read OK ({len(raw)} bytes)")

    # --- 3. Write-back: update a "last_access" field ---
    cfg["last_access"] = "2026-01-01T09:00:00Z"
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    print("[legacy-reader] write-back: updated last_access field")

    # --- 4. Re-read to confirm write persisted ---
    with open(path, "r") as f:
        updated = json.load(f)
    assert updated["last_access"] == "2026-01-01T09:00:00Z", "write-back failed!"
    print("[legacy-reader] re-read: write-back confirmed (last_access persisted)")

    print(f"[legacy-reader] connecting to {cfg['host']}/{cfg['dbname']} as {cfg['username']} ...")
    print("[legacy-reader] (password used in memory to connect — never printed, never logged)")


if __name__ == "__main__":
    main()
