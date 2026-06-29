#!/usr/bin/env python3
"""legacy_reader.py — the app WE CANNOT CHANGE.

All it knows is: read a config file at a path and use the credentials inside.
It has no idea the "file" is actually a named pipe (FIFO) — that obliviousness
is the whole point: we deliver the secret WITHOUT touching the reader.

It finds its config two ways:
    CONFIG_PATH=/path ./legacy_reader.py     # via environment
    ./legacy_reader.py                        # falls back to a hard-coded path
"""
import json
import os
import sys
from pathlib import Path

HARDCODED = Path(__file__).resolve().parent / "run" / "secrets.json"


def config_path() -> Path:
    if os.environ.get("CONFIG_PATH"):
        return Path(os.environ["CONFIG_PATH"])
    return HARDCODED


def die(msg: str):
    bar = "!" * 64
    print(f"\n{bar}", file=sys.stderr)
    print(f"[legacy-reader] FATAL: {msg}", file=sys.stderr)
    print("[legacy-reader] No secret, no service.", file=sys.stderr)
    print(f"{bar}\n", file=sys.stderr)
    sys.exit(2)


path = config_path()
if not path.exists():
    die(f"cannot find my config file: {path}")
try:
    cfg = json.load(open(path))
except Exception as e:  # noqa: BLE001
    die(f"config unreadable: {path}: {e}")

print(f"[legacy-reader] opened {path}")
print(f"[legacy-reader] connecting to {cfg['host']}/{cfg['dbname']} as {cfg['username']} ...")
print("[legacy-reader] (password used in memory to connect — never printed, never logged)")
