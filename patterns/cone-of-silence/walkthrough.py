"""walkthrough.py — the Cone of Silence walkthrough as DATA (realizes BACKLOG #6).

Single source of truth, rendered two ways:
  - demonstrate.py        -> the interactive TUI (runs the live commands; ignores `out`)
  - tools/build_deck.py   -> a static HTML slide deck (renders `out`; ignores `colorize`)

A walkthrough is a list of beats, keyed by (state, act):

  {"say": str}                          narration
  {"cmd": str, "out": str,              a command. The TUI runs it (colorized per
   "colorize": "ls"|"grep"|"cat"}       `colorize`); the deck shows `cmd` + the frozen `out`.
  {"verdict": str, "ok": bool}          the capping success / failure line

`out` is FROZEN, representative output authored for the deck — NOT captured live — so the
deck is deterministic (no real $PS1, no `ls` timestamps, no current `df` mounts). The TUI
always shows the real thing. The deck renders every command at DEMO_PROMPT, a fixed prompt.
"""

# These mirror cone.py's fixed constants (CONE=/dev/shm/cone-of-silence, NEEDLE).
SECRET      = "/dev/shm/cone-of-silence/secrets.json"
NEEDLE      = "S3cr3t-Pg-Pass"
DEMO_PROMPT = "[you@host cone-of-silence]$ "

GREP = (f"grep -rn '{NEEDLE}' . --exclude='*.py' --exclude='*.pyc' "
        f"--exclude='*.html' --exclude='*.md' --exclude-dir='__pycache__' "
        f"|| echo '    (nothing found on disk)'")

_BAR = "!" * 64

def _reader_ok(path):
    return (f"[legacy-reader] opened {path}\n"
            f"[legacy-reader] connecting to db.internal/appdb as app_pg_user ...\n"
            f"[legacy-reader] (password used in memory to connect — never printed, never logged)")

def _reader_fatal(path):
    return (f"{_BAR}\n"
            f"[legacy-reader] FATAL: cannot find my config file: {path}\n"
            f"[legacy-reader] No secret, no service. (Is the Cone disengaged?)\n"
            f"{_BAR}")

_LS = """total 88
drwxr-xr-x 3 you you  4096 Jan  1 09:00 .
drwxr-xr-x 4 you you  4096 Jan  1 09:00 ..
-rw-r--r-- 1 you you   140 Jan  1 09:00 .gitignore
-rw-r--r-- 1 you you  1820 Jan  1 09:00 BACKLOG.md
-rw-r--r-- 1 you you 11402 Jan  1 09:00 NOTES.md
-rw-r--r-- 1 you you  4011 Jan  1 09:00 README.md
-r-------- 1 you you    44 Jan  1 09:00 cone.key
-rwxr-xr-x 1 you you  5102 Jan  1 09:00 cone.py
-rw-r--r-- 1 you you 21044 Jan  1 09:00 deck.html
-rwxr-xr-x 1 you you  9120 Jan  1 09:00 demonstrate.py
-rw-r--r-- 1 you you 12880 Jan  1 09:00 enlighten.html
drwx------ 2 you you  4096 Jan  1 09:00 legacy-etc
-rwxr-xr-x 1 you you  1903 Jan  1 09:00 legacy_reader.py
-rw-r--r-- 1 you you   228 Jan  1 09:00 secrets.json.enc
-rw-r--r-- 1 you you  3650 Jan  1 09:00 walkthrough.py"""

_DF = """Filesystem      Size  Used Avail Use% Mounted on
tmpfs           2.8G  4.5M  2.8G   1% /run
tmpfs            14G  4.0K   14G   1% /dev/shm
tmpfs           5.0M     0  5.0M   0% /run/lock
tmpfs           2.8G  5.1M  2.8G   1% /run/user/1000"""

_DF_SECRET = """Filesystem      Size  Used Avail Use% Mounted on
tmpfs            14G  4.0K   14G   1% /dev/shm"""

_SECRET_JSON = """{
  "username": "app_pg_user",
  "passwd": "S3cr3t-Pg-Pass",
  "host": "db.internal",
  "dbname": "appdb"
}"""

WALKTHROUGH = {
    ("engaged", "read"): [
        {"say": "The Cone of Silence is in place. Our legacy app reaches her secret the old\n"
                "cleartext way — with no knowledge or awareness of encryption.\n"
                "Only the ENCRYPTED file lives on disk; let's look:"},
        {"cmd": "ls -la", "colorize": "ls", "out": _LS},
        {"say": "...yet a cleartext secret is readable. Where? A memory-only filesystem —\n"
                "the Cone of Silence. Here are the tmpfs (RAM) mounts:"},
        {"cmd": "df -h -t tmpfs", "out": _DF},
        {"say": "Our legacy_reader.py starts up exactly as she always has:"},
        {"cmd": f"./legacy_reader.py --config {SECRET}", "out": _reader_ok(SECRET)},
        {"say": "And via a softlink at her HARD-CODED path, she runs with NO arguments, too! —\n"
                "So apps with hard-coded filepaths are supported as well:"},
        {"cmd": "./legacy_reader.py", "out": _reader_ok("legacy-etc/secrets.json")},
        {"verdict": "legacy_reader_py reads her secret. Nothing on disk changed.", "ok": True},
    ],
    ("engaged", "detect"): [
        {"say": "The app just read the secret. So it must be on disk somewhere, right?\n"
                "Lets hunt through the whole directory for the password:"},
        {"cmd": GREP, "colorize": "grep", "out": "    (nothing found on disk)"},
        {"say": "Nothing on disk. The cleartext lives ONLY inside the Cone (RAM). Proof:"},
        {"cmd": f"cat {SECRET}", "colorize": "cat", "out": _SECRET_JSON},
        {"cmd": f"df -h {SECRET}", "out": _DF_SECRET},
        {"verdict": "Readable by the app, invisible to the disk. That is the whole trick.", "ok": True},
    ],
    ("disengaged", "read"): [
        {"say": "The Cone of Silence is lifted. The secret has evaporated from RAM.\n"
                "Only ciphertext remains on disk:"},
        {"cmd": "ls -la", "colorize": "ls", "out": _LS},
        {"say": "Watch the legacy app try to start with the Cone disengaged — no secret to be had:"},
        {"cmd": f"./legacy_reader.py --config {SECRET}", "out": _reader_fatal(SECRET)},
        {"say": "It is the same at her hard-coded path — the softlink is gone, so she fails loudly:"},
        {"cmd": "./legacy_reader.py", "out": _reader_fatal("legacy-etc/secrets.json")},
        {"verdict": "No Cone, no service — loud, early failures make it easy to see what happened.", "ok": False},
    ],
    ("disengaged", "detect"): [
        {"say": "The Cone is lifted. Hunt the disk for the password once more:"},
        {"cmd": GREP, "colorize": "grep", "out": "    (nothing found on disk)"},
        {"say": "And the Cone itself is empty:"},
        {"cmd": "ls -la /dev/shm/cone-of-silence 2>/dev/null || echo '    (the Cone is gone)'",
         "out": "    (the Cone is gone)"},
        {"say": "Nothing, anywhere. On disk: only ciphertext. In RAM: nothing."},
    ],
}
