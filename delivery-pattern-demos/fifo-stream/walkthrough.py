"""walkthrough.py — the fifo-stream slide deck as DATA.

`tools/build_deck.py` renders `SLIDES` -> a self-contained, deterministic `deck.html`.
The frozen `out` strings are representative output (not live-captured) so the deck is
byte-identical on every machine. The interactive TUI (`demonstrate.py`) runs the same
commands for real.

Beats (same vocabulary as the deck renderer):
  {"title", "tagline", "kicker"}   the cover slide
  {"say": str}                     narration
  {"prose": str}                   body text
  {"cmd": str, "out": str}         a command shown at the demo prompt + its (frozen) output
  {"verdict": str, "ok": bool}     the capping success/failure line
  {"html": str}                    raw html (closing links)
"""

DEMO_PROMPT = "[you@host fifo-stream]$ "

NEEDLE = "S3cr3t-Pg-Pass"
FIFO_PATH = "/tmp/fifo-stream-demo/secrets.json"

_READER_OK = (
    f"[legacy-reader] opened {FIFO_PATH}\n"
    f"[legacy-reader] connecting to db.internal/appdb as app_pg_user ...\n"
    "[legacy-reader] (password used in memory to connect — never printed, never logged)"
)

SLIDES = [
    {"title": None, "beats": [
        {"title": "FIFO Stream",
         "tagline": "named-pipe zero-disk secret delivery",
         "kicker": "legacy-secrets-adapters · a walkthrough"}]},

    {"title": "The problem", "beats": [
        {"prose": "A legacy app reads its credentials from a file at a fixed path. Even a RAM-backed "
                  "tmpfs file can be read by root or another process sharing the mount. For a "
                  "read-once sequential reader, we can do better: deliver the secret through a "
                  "named pipe (FIFO) so it streams through kernel memory and NEVER exists on any "
                  "filesystem — not even tmpfs."}]},

    {"title": "Create the named pipe", "beats": [
        {"say": "Replace the file the reader expects with a FIFO at the same path.\n"
                "A FIFO looks like a file but is a kernel pipe buffer — no data stored anywhere."},
        {"cmd": f"mkfifo {FIFO_PATH}",
         "out": ""},
        {"cmd": f"ls -la {FIFO_PATH}",
         "out": f"prw------- 1 you you 0 Jan  1 09:00 {FIFO_PATH}"},
        {"say": "Note the 'p' at the start — that's a pipe, not a regular file."}]},

    {"title": "Writer feeds, reader reads", "beats": [
        {"say": "The writer pushes the secret into the pipe. The reader opens the same path\n"
                "and receives the secret — streaming through kernel memory, never touching disk."},
        {"cmd": f"echo '{{\"passwd\": \"{NEEDLE}\", ...}}' > {FIFO_PATH} &",
         "out": "[1] 12345"},
        {"cmd": f"CONFIG_PATH={FIFO_PATH} ./legacy_reader.py",
         "out": _READER_OK},
        {"verdict": "The reader gets the secret — delivered through the pipe, never stored.", "ok": True}]},

    {"title": "Grep the disk — nothing", "beats": [
        {"say": "The secret streamed through kernel memory. There is no file to grep,\n"
                "no data on disk, no tmpfs remnant — nothing."},
        {"cmd": f"grep -r '{NEEDLE}' /tmp/fifo-stream-demo/ --exclude='*.py' || echo '    (nothing found)'",
         "out": "    (nothing found)"},
        {"say": "A FIFO has no content — it's a rendezvous point, not a container. The secret\n"
                "existed only in the kernel pipe buffer while data was in flight."},
        {"verdict": "Zero disk footprint. Not even a tmpfs file to protect.", "ok": True}]},

    {"title": "Second cat hangs (read-once)", "beats": [
        {"say": "A named pipe is read-once by nature. Once the data flows through, there is\n"
                "nothing left to read — a second reader blocks forever (until a new writer appears)."},
        {"cmd": f"cat {FIFO_PATH}   # hangs — no writer, nothing buffered",
         "out": "^C  (interrupted after 5s — the cat hung, proving read-once)"},
        {"verdict": "Read-once: the secret flows through once and is gone. No replay possible.", "ok": True}]},

    {"title": "The takeaway", "beats": [
        {"prose": "A named pipe (FIFO) delivers a secret with zero disk footprint — the data streams "
                  "through kernel memory and never exists on any filesystem. The legacy app opens the "
                  "same path it always did; it has no idea the 'file' is a pipe."},
        {"prose": "Tradeoffs: read-once (the app can't re-read the file), timing coordination (the "
                  "writer must feed before or concurrently with the reader), and no persistence (a "
                  "restart needs a new write). Stronger than tmpfs for sequential, read-once readers."},
        {"html": '<p class="prose"><strong>Bootstrap secret — out of scope.</strong> How the writer '
                 'obtains the secret to feed into the pipe is an orthogonal concern (the bootstrap-secret '
                 'pattern family). Why &amp; what: <code>enlighten.html</code> · '
                 '<a href="https://github.com/Wave-Engineering/legacy-secrets-adapters">the catalog</a>.</p>'}]},
]
