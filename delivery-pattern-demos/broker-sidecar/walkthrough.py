"""walkthrough.py — the broker-sidecar slide deck as DATA.

`tools/build_deck.py` renders `SLIDES` -> a self-contained, deterministic `deck.html`.
The frozen `out` strings are REAL output captured from a live OpenBao run, with timestamps
and values frozen so the deck is byte-identical on every machine. The interactive TUI
(`demonstrate.py`) runs the same commands for real against the local container stack.

Beats (same vocabulary as the deck renderer):
  {"title", "tagline", "kicker"}   the cover slide
  {"say": str}                     narration
  {"prose": str}                   body text
  {"cmd": str, "out": str}         a command shown at the demo prompt + its (frozen) output
  {"verdict": str, "ok": bool}     the capping success/failure line
  {"html": str}                    raw html (closing links)
"""

DEMO_PROMPT = "[you@host broker-sidecar]$ "

_READER_OK_V1 = (
    "[legacy-reader] opened db.conf; found credential for app_pg_user@127.0.0.1:5432/appdb\n"
    "[legacy-reader] password value: S3cr3t-Pg-Pass\n"
    "[legacy-reader] (in production this would be used to connect — never printed)"
)

_READER_OK_V2 = (
    "[legacy-reader] opened db.conf; found credential for app_pg_user@127.0.0.1:5432/appdb\n"
    "[legacy-reader] password value: R0tated-Pg-Pass-v2\n"
    "[legacy-reader] (in production this would be used to connect — never printed)"
)

SLIDES = [
    {"title": None, "beats": [
        {"title": "Broker Sidecar",
         "tagline": "a generalized vault-materialization sidecar with templating and rotation watch",
         "kicker": "legacy-secrets-adapters · a walkthrough"}]},

    {"title": "The problem", "beats": [
        {"prose": "A legacy app reads credentials from a config file in its own format. The secret "
                  "must come from a vault, rendered into THAT format, and refreshed when it rotates — "
                  "all without touching the app. The dynamic-credential-shim solved this for one shape "
                  "(a JSON secrets file + a Postgres static role). The BROKER generalizes: any secret, "
                  "any template, any format."}]},

    {"title": "How this generalizes the shim", "beats": [
        {"prose": "The dynamic-credential-shim is a PURPOSE-BUILT fetcher: one secret type "
                  "(database/static-creds), one output format (JSON), one lifecycle (manual re-run). "
                  "The broker sidecar is the GENERALIZED form:"},
        {"prose": "1. Fetch ANY secret from KV v2 (not just database credentials)\n"
                  "2. Render through a Jinja2 TEMPLATE (the app's native config format)\n"
                  "3. POLL for version changes and re-render automatically\n"
                  "4. Log lifecycle events (fetch, render, rotation)"},
        {"prose": "Same principle — a sidecar materializes what the app reads — but now it works "
                  "for any secret shape the vault can store."}]},

    {"title": "Bring up OpenBao + seed the secret", "beats": [
        {"say": "Real OpenBao (dev mode) in a container. The root token is an obvious dev value —\n"
                "a bootstrap secret, out of scope (see the README)."},
        {"cmd": "docker compose up -d",
         "out": " ✔ Container broker-sidecar-openbao-1  Started"},
        {"say": "Seed a secret into KV v2 at secret/apps/legacy-db:"},
        {"cmd": "python3 -c \"import demo; demo.seed_secret(demo.INITIAL_SECRET)\"",
         "out": ""},
        {"say": "The secret is now in OpenBao: host, port, dbname, username, password (S3cr3t-Pg-Pass)."}]},

    {"title": "Broker fetches and renders", "beats": [
        {"say": "The broker fetches the secret and renders it through templates/db.conf.j2\n"
                "into the file the legacy app reads (run/db.conf):"},
        {"cmd": "./broker.py",
         "out": "[broker] fetched secret v1, rendered db.conf.j2 -> run/db.conf"},
        {"say": "The rendered output is a standard INI config — the app's native format:"},
        {"cmd": "cat run/db.conf",
         "out": "# Database configuration — rendered by the broker sidecar.\n"
                "# The legacy app reads this file; the broker keeps it fresh.\n"
                "[database]\n"
                "host = 127.0.0.1\n"
                "port = 5432\n"
                "dbname = appdb\n"
                "username = app_pg_user\n"
                "password = S3cr3t-Pg-Pass"}]},

    {"title": "The legacy reader connects — unchanged", "beats": [
        {"say": "The legacy reader opens its config file and reads the credential.\n"
                "It has no idea a broker sidecar put it there:"},
        {"cmd": "./legacy_reader.py", "out": _READER_OK_V1},
        {"verdict": "The reader got a vault-managed credential without any code change.", "ok": True}]},

    {"title": "Rotate — broker detects and re-renders", "beats": [
        {"say": "Simulate rotation: write a new version of the secret to KV v2\n"
                "(in production, an operator or automation writes the new value):"},
        {"cmd": "python3 -c \"import demo; demo.seed_secret(demo.ROTATED_SECRET)\"",
         "out": ""},
        {"say": "The broker fetches again — it sees v2, re-renders the template:"},
        {"cmd": "./broker.py",
         "out": "[broker] fetched secret v2, rendered db.conf.j2 -> run/db.conf"},
        {"say": "The reader (unchanged) sees the new credential:"},
        {"cmd": "./legacy_reader.py", "out": _READER_OK_V2},
        {"verdict": "Rotation detected, re-rendered, reader sees the new value — no code touched.", "ok": True}]},

    {"title": "The takeaway", "beats": [
        {"prose": "The broker sidecar is the GENERALIZED delivery pattern: authenticate to a vault, "
                  "fetch any secret, render it through a template into whatever format the app reads, "
                  "and watch for rotation. The app never changes — only what's behind its config file."},
        {"prose": "The dynamic-credential-shim is a SPECIAL CASE of this pattern: a broker whose "
                  "template is hardcoded as JSON and whose secret source is the database engine. "
                  "The sidecar trades that specificity for universality."},
        {"html": '<p class="prose"><strong>Bootstrap secret — out of scope.</strong> The OpenBao token here '
                 'is an obvious dev value; how the broker would really authenticate is an orthogonal concern '
                 '(the bootstrap-secret pattern family). Why &amp; what: <code>enlighten.html</code> · '
                 '<a href="https://github.com/Wave-Engineering/legacy-secrets-adapters">the catalog</a>.</p>'}]},
]
