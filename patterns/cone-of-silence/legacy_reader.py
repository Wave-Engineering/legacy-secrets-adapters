#!/usr/bin/env python3
"""legacy-reader — the app WE CANNOT CHANGE.

All it knows how to do is read a config file and use the secret inside it.
It has no idea about encryption, RAM, tmpfs, or where the file came from.
That obliviousness is the whole point: we protect the secret WITHOUT touching it.

It finds its config three ways (all "legacy-normal"):
    ./legacy_reader.py --config /path/to/secrets.json   # told explicitly
    CONFIG_PATH=/path ./legacy_reader.py                 # via environment
    ./legacy_reader.py                                   # its baked-in hard-coded path
"""
import json
import os
import sys
from pathlib import Path

# The path this app was shipped with years ago. Apps like this often can't be
# reconfigured — which is why the Cone setup drops a softlink here (see demonstrate.py).
HARDCODED = Path(__file__).resolve().parent / "legacy-etc" / "secrets.json"


def config_path() -> Path:
    argv = sys.argv[1:]
    if "--config" in argv:
        return Path(argv[argv.index("--config") + 1])
    if os.environ.get("CONFIG_PATH"):
        return Path(os.environ["CONFIG_PATH"])
    return HARDCODED


def die(msg: str):
    bar = "!" * 64
    print(f"\n{bar}", file=sys.stderr)
    print(f"[legacy-reader] FATAL: {msg}", file=sys.stderr)
    print("[legacy-reader] No secret, no service. (Is the Cone disengaged?)", file=sys.stderr)
    print(f"{bar}\n", file=sys.stderr)
    sys.exit(2)


path = config_path()
if not path.exists():
    die(f"cannot find my config file: {path}")
try:
    cfg = json.load(open(path))
except Exception as e:  # noqa: BLE001 — a legacy app would just bail
    die(f"config unreadable: {path}: {e}")

print(f"[legacy-reader] opened {path}")
print(f"[legacy-reader] connecting to {cfg['host']}/{cfg['dbname']} as {cfg['username']} ...")
print("[legacy-reader] (password used in memory to connect — never printed, never logged)")
