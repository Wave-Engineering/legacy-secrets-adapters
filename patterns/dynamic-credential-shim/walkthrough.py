"""walkthrough.py — the dynamic-credential-shim slide deck as DATA.

`tools/build_deck.py` renders `SLIDES` → a self-contained, deterministic `deck.html`.
The frozen `out` strings are REAL output captured from a live OpenBao + Postgres run, with the
timestamp and password frozen so the deck is byte-identical on every machine. The interactive
TUI (`demonstrate.py`) runs the same commands for real against the local container stack.

Beats (same vocabulary as the deck renderer):
  {"title", "tagline", "kicker"}   the cover slide
  {"say": str}                     narration
  {"prose": str}                   body text
  {"cmd": str, "out": str}         a command shown at the demo prompt + its (frozen) output
  {"verdict": str, "ok": bool}     the capping success/failure line
  {"html": str}                    raw html (closing links)
"""

DEMO_PROMPT = "[you@host dynamic-credential-shim]$ "

_READER_OK = (
    "[legacy-reader] opened secrets.json; connecting to 127.0.0.1:55432/appdb as app_pg_user ...\n"
    "[legacy-reader] connected OK as app_pg_user|2026-01-01 09:00:00+00\n"
    "[legacy-reader] (password used in memory to connect — never printed, never logged)"
)

SLIDES = [
    {"title": None, "beats": [
        {"title": "Dynamic Credential Shim",
         "tagline": "a static DB password → an OpenBao-managed credential that rotates, so a leak self-expires",
         "kicker": "legacy-secrets-adapters · a walkthrough"}]},

    {"title": "The problem", "beats": [
        {"prose": "A legacy app reads a STATIC Postgres password from a file and won't be re-released. "
                  "That password is valid forever — so a single leak (a backup, a log, a stolen disk) is "
                  "valid forever too. We want the credential to ROTATE and a leak to self-expire — without "
                  "touching the app."}]},

    {"title": "Bring up OpenBao + Postgres", "beats": [
        {"say": "Real OpenBao (dev mode) + Postgres in containers. The OpenBao token and the PG superuser\n"
                "password here are obvious dev values — bootstrap secrets, out of scope (see the README)."},
        {"cmd": "docker compose up -d",
         "out": " ✔ Container dynamic-credential-shim-postgres-1  Healthy\n"
                " ✔ Container dynamic-credential-shim-openbao-1   Started"},
        {"say": "Configure the database secrets engine and a STATIC role — OpenBao now owns and rotates\n"
                "the password of one fixed Postgres user, app_pg_user:"},
        {"cmd": "./setup.sh",
         "out": "→ creating the fixed app role OpenBao will manage (app_pg_user)\n"
                "→ enabling + configuring the database secrets engine\n"
                "→ rotating OpenBao's own admin password (now no human knows it)\n"
                "→ defining the STATIC role (OpenBao owns + rotates app_pg_user's password)\n"
                "✅ setup complete"}]},

    {"title": "The managed credential works", "beats": [
        {"say": "The shim fetches the current managed credential and writes the file the reader reads:"},
        {"cmd": "./shim.py",
         "out": "→ shim: wrote OpenBao-managed credential for 'app_pg_user' to run/secrets.json"},
        {"say": "The unchanged legacy reader connects — it has no idea the password is managed or rotates:"},
        {"cmd": "./legacy_reader.py", "out": _READER_OK}]},

    {"title": "Rotate — and the leaked copy dies", "beats": [
        {"say": "Say an attacker exfiltrates a copy of the current password. Then OpenBao rotates the\n"
                "static role (here we force it; in production it's a schedule):"},
        {"cmd": "bao write -f database/rotate-role/app-static",
         "out": "Success! Data written to: database/rotate-role/app-static"},
        {"say": "The exfiltrated copy no longer authenticates:"},
        {"cmd": "psql 'postgresql://app_pg_user:<exfiltrated>@127.0.0.1:55432/appdb' -tAc 'select 1'",
         "out": 'psql: error: connection to server at "127.0.0.1", port 55432 failed:\n'
                'FATAL:  password authentication failed for user "app_pg_user"'},
        {"verdict": "The leak self-expired. A stolen credential is dead within one rotation window.", "ok": True}]},

    {"title": "The app keeps working — untouched", "beats": [
        {"say": "The shim re-materializes the new password; the reader (unchanged) reconnects:"},
        {"cmd": "./shim.py",
         "out": "→ shim: wrote OpenBao-managed credential for 'app_pg_user' to run/secrets.json"},
        {"cmd": "./legacy_reader.py", "out": _READER_OK}]},

    {"title": "The takeaway", "beats": [
        {"prose": "Static password → a leak is valid forever. An OpenBao-managed STATIC role → a fixed "
                  "username (pool-friendly), a password OpenBao rotates, and a leaked copy that self-expires "
                  "within a rotation window. The app never changed — only what's behind its file did."},
        {"prose": "Dynamic roles (a brand-new Postgres user per short lease) are a small extension of this — "
                  "left to the reader. They harden the leak window further but the changing username can "
                  "break a legacy connection pool; see NOTES.md."},
        {"html": '<p class="prose"><strong>Bootstrap secret — out of scope.</strong> The OpenBao token here '
                 'is an obvious dev value; how the shim would really authenticate is an orthogonal concern '
                 '(the bootstrap-secret pattern family). Why &amp; what: <code>enlighten.html</code> · '
                 'deep-dive: <code>NOTES.md</code> · '
                 '<a href="https://github.com/Wave-Engineering/legacy-secrets-adapters">the catalog</a>.</p>'}]},
]
