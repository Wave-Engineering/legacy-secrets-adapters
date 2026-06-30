"""walkthrough.py — the fuse-decrypt slide deck as DATA.

`tools/build_deck.py` renders `SLIDES` -> a self-contained, deterministic `deck.html`.
The frozen `out` strings are representative output authored for the deck — NOT captured
live — so the deck is byte-identical on every machine.

Beats (same vocabulary as the deck renderer):
  {"title", "tagline", "kicker"}   the cover slide
  {"say": str}                     narration
  {"prose": str}                   body text
  {"cmd": str, "out": str}         a command shown at the demo prompt + its (frozen) output
  {"verdict": str, "ok": bool}     the capping success/failure line
  {"html": str}                    raw html (closing links)
"""

DEMO_PROMPT = "[you@host fuse-decrypt]$ "

NEEDLE = "S3cr3t-Pg-Pass"

_READER_OK = (
    "[legacy-reader] opened mnt/secrets.json\n"
    "[legacy-reader] read credentials for app_pg_user@db.internal/appdb\n"
    "[legacy-reader] seek test: file size=109, re-read OK (109 bytes)\n"
    "[legacy-reader] write-back: updated last_access field\n"
    "[legacy-reader] re-read: write-back confirmed (last_access persisted)\n"
    "[legacy-reader] connecting to db.internal/appdb as app_pg_user ...\n"
    "[legacy-reader] (password used in memory to connect — never printed, never logged)"
)

_HEXDUMP = (
    "0000  a3 f1 2c 8e 01 bb 47 d9  e2 10 3a 5c 94 17 e8 2b  ..,...G...:....+\n"
    "0010  6a c0 dd 91 f4 55 83 0e  7b 29 a1 4d 68 3f 5a b2  j....U..{).Mh?Z.\n"
    "0020  9f 0c 73 e6 d8 24 ab 60  15 8d 4e f9 c7 36 71 08  ..s..$.`..N..6q.\n"
    "0030  dc b4 42 85 a7 6e 13 cf  50 39 2d fd 88 7a e5 1b  ..B..n..P9-..z..\n"
    "0040  03 46 9a 2e f0 61 bc 5d  d4 78 0f 93 67 a4 1c e9  .F...a.].x..g...\n"
    "0050  3b 52 c8 06 7d b5 48 de  22 96 59 af 0a 74 e3 30  ;R..}.H.\".Y..t.0\n"
    "0060  84 cb 4f 1d f6 63 8a 37  be 51 d2 09 75 ac 40 ee  ..O..c.7.Q..u.@.\n"
    "0070  18 5f c4 6b 33 97 da 0d  a0 62 b8 45 f3 2a 81 56  ._.k3....b.E.*.V\n"
    "    ... (141 bytes total)"
)

SLIDES = [
    {"title": None, "beats": [
        {"title": "FUSE Decrypt",
         "tagline": "a transparent decrypt-on-read filesystem for legacy apps with arbitrary I/O",
         "kicker": "legacy-secrets-adapters · a walkthrough"}]},

    {"title": "The problem", "beats": [
        {"prose": "A legacy app reads credentials from a plaintext file on disk — but does MORE than "
                  "a single sequential read. It seeks, writes back, re-reads, and expects full POSIX "
                  "semantics. A pipe or single-read shim cannot satisfy it. We need a real filesystem "
                  "that decrypts on the fly — without touching the app."}]},

    {"title": "Encrypt the secret to disk", "beats": [
        {"say": "First, we create the ciphertext backing store. The plaintext secret is encrypted\n"
                "with AES-256-GCM; only ciphertext is stored on disk."},
        {"cmd": "python3 -c \"import fusefs, json; ...\"  # (setup)",
         "out": "-> encrypted secrets.json to cipherstore/ (AES-256-GCM, 141 bytes)"}]},

    {"title": "Verify: disk holds only ciphertext", "beats": [
        {"say": "The backing file is pure ciphertext — the password is not present:"},
        {"cmd": f"grep '{NEEDLE}' cipherstore/secrets.json || echo '(not found)'",
         "out": "(not found)"},
        {"say": "A hex dump confirms it is binary gibberish:"},
        {"cmd": "xxd cipherstore/secrets.json | head -8",
         "out": _HEXDUMP}]},

    {"title": "Mount the FUSE filesystem", "beats": [
        {"say": "The FUSE daemon mounts the cipherstore as a plaintext view. The key is held\n"
                "in memory — never on disk in production (here: a demo keyfile)."},
        {"cmd": "python3 fusefs.py cipherstore/ mnt/ demo.key &",
         "out": "mounting cipherstore/ -> mnt/ (AES-256-GCM, decrypt-on-read)"}]},

    {"title": "Read through the mount — plaintext!", "beats": [
        {"say": "The legacy reader opens the file at its expected path (inside the mount).\n"
                "It sees plaintext — and exercises seek + write-back:"},
        {"cmd": "./legacy_reader.py --config mnt/secrets.json",
         "out": _READER_OK},
        {"verdict": "The reader sees plaintext through the mount. Seek + write-back work.", "ok": True}]},

    {"title": "Disk is STILL ciphertext after a write", "beats": [
        {"say": "The reader wrote back through the mount. What happened on disk?"},
        {"cmd": f"grep '{NEEDLE}' cipherstore/secrets.json || echo '(not found)'",
         "out": "(not found)"},
        {"verdict": "Write-back went through FUSE -> encrypted on disk. No plaintext leaked.", "ok": True}]},

    {"title": "Unmount -> remount round-trip", "beats": [
        {"say": "Unmount, then remount. Data is persisted as ciphertext — the round-trip works:"},
        {"cmd": "fusermount3 -u mnt/ && python3 fusefs.py cipherstore/ mnt/ demo.key &",
         "out": "mounting cipherstore/ -> mnt/ (AES-256-GCM, decrypt-on-read)"},
        {"cmd": "cat mnt/secrets.json | python3 -c \"import json,sys; d=json.load(sys.stdin); print(d['passwd'][:4]+'...')\"",
         "out": "S3cr..."},
        {"verdict": "Remount confirmed — ciphertext persists, plaintext view restored.", "ok": True}]},

    {"title": "The takeaway", "beats": [
        {"prose": "Ciphertext at rest. Plaintext only through the FUSE mount — in memory, never on disk. "
                  "The app does arbitrary POSIX I/O (seek, write, re-read) and never knows. "
                  "The key lives in the daemon's memory; unmount = no plaintext anywhere."},
        {"prose": "The FUSE layer handles the hardest access pattern in the catalog: full POSIX semantics. "
                  "Simpler patterns (Cone of Silence, fifo-stream) cover simpler readers. "
                  "fuse-decrypt is the nuclear option — when nothing else fits."},
        {"html": '<p class="prose"><strong>Bootstrap secret — out of scope.</strong> The AES key here '
                 'is a demo keyfile; how the daemon would really obtain it (TPM, OpenBao transit) is an '
                 'orthogonal concern. Why &amp; what: <code>enlighten.html</code> · '
                 '<a href="https://github.com/Wave-Engineering/legacy-secrets-adapters">the catalog</a>.</p>'}]},
]
