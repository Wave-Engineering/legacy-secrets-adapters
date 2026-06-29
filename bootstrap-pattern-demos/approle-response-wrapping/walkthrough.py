"""walkthrough.py — the approle-response-wrapping slide deck as DATA.

`tools/build_deck.py` renders `SLIDES` -> a self-contained, deterministic `deck.html`.
The frozen `out` strings are REAL output captured from a live OpenBao run, with tokens
and timestamps frozen so the deck is byte-identical on every machine. The interactive
TUI (`demonstrate.py`) runs the same commands for real against the local container.

Beats (same vocabulary as the deck renderer):
  {"title", "tagline", "kicker"}   the cover slide
  {"say": str}                     narration
  {"prose": str}                   body text
  {"cmd": str, "out": str}         a command shown at the demo prompt + its (frozen) output
  {"verdict": str, "ok": bool}     the capping success/failure line
  {"html": str}                    raw html (closing links)
"""

DEMO_PROMPT = "[you@host approle-response-wrapping]$ "

SLIDES = [
    {"title": None, "beats": [
        {"title": "AppRole Response-Wrapping",
         "tagline": "a single-use wrapped token bootstrap — replay-proof, time-limited, no stored secret",
         "kicker": "legacy-secrets-adapters · a walkthrough"}]},

    {"title": "The bootstrap problem", "beats": [
        {"prose": "A materializer needs to authenticate to its key source (OpenBao) without a stored "
                  "secret. If you bake the secret into the image or drop it on disk, anyone who steals "
                  "the disk steals the identity. The question: how do you deliver a credential that "
                  "is DEAD on replay and DEAD after a short window?"},
        {"prose": "Answer: response-wrap a SecretID. The wrapping token is single-use (consumed on first "
                  "unwrap) and short-lived (TTL). A trusted deployer generates it; the materializer "
                  "consumes it exactly once."}]},

    {"title": "Bring up OpenBao + configure AppRole", "beats": [
        {"say": "[deployer] Real OpenBao in dev mode. The root token here is the obvious dev value\n"
                "this pattern replaces in production."},
        {"cmd": "docker compose up -d",
         "out": " ✔ Container approle-response-wrapping-openbao-1  Started"},
        {"say": "[deployer] Enable AppRole auth, create the role + policy, write a demo secret:"},
        {"cmd": "# (programmatic setup via demo.py — enable approle, create role, write secret)",
         "out": "[setup] Enabling AppRole auth method ...\n"
                "[setup] Creating AppRole role 'demo-app' ...\n"
                "[setup] Creating policy 'demo-app-policy' ...\n"
                "[setup] Writing demo secret ...\n"
                "[setup] Fetching RoleID ...\n"
                "[setup] RoleID saved to run/role-id"}]},

    {"title": "Deployer wraps SecretID (Ansible)", "beats": [
        {"say": "[deployer] The Ansible playbook generates a response-wrapped SecretID\n"
                "and delivers the wrapping token to the target. TTL=30s, single-use."},
        {"cmd": "ansible-playbook -i inventory.yml playbook.yml",
         "out": "PLAY [Wrap and deliver AppRole SecretID] ***\n\n"
                "TASK [Ensure run directory exists] ***\n"
                "ok: [localhost]\n\n"
                "TASK [Generate response-wrapped SecretID] ***\n"
                "ok: [localhost]\n\n"
                "TASK [Deliver wrapped token to target] ***\n"
                "changed: [localhost]\n\n"
                "TASK [Report delivery] ***\n"
                'ok: [localhost] => msg: "Wrapped SecretID delivered to run/wrapped-token '
                '(TTL=30s, single-use, accessor=hmac-v1:abc...)"'},
        {"verdict": "Wrapping token delivered. It can be unwrapped exactly once, within 30s.", "ok": True}]},

    {"title": "Materializer unwraps + authenticates", "beats": [
        {"say": "[target] The materializer reads the wrapping token, unwraps it to get the\n"
                "SecretID, then authenticates via AppRole (RoleID + SecretID) and fetches the secret."},
        {"cmd": "python3 materializer.py",
         "out": "[materializer] unwrapping token to obtain SecretID ...\n"
                "[materializer] SecretID obtained (single-use token consumed)\n"
                "[materializer] authenticating via AppRole (RoleID + SecretID) ...\n"
                "[materializer] authenticated — got client token\n"
                "[materializer] fetching secret from secret/data/demo-app/config ...\n"
                "[materializer] secret retrieved: keys=['password', 'host']\n"
                "[materializer] (password used in memory — never printed, never logged)"},
        {"verdict": "Materializer authenticated without a stored secret.", "ok": True}]},

    {"title": "Replay fails — single-use", "beats": [
        {"say": "[attacker] What if someone steals the wrapping token after delivery?\n"
                "They try to unwrap it again:"},
        {"cmd": "# attempt to unwrap the same token a second time",
         "out": "Error: wrapping token is not valid or does not exist (HTTP 400)"},
        {"verdict": "Single-use: consumed on first unwrap. Replay is impossible.", "ok": True}]},

    {"title": "Expired token fails — TTL", "beats": [
        {"say": "[attacker] What if they intercept the token before the materializer gets it,\n"
                "but wait too long?"},
        {"cmd": "# generate a token with TTL=2s, wait 3s, attempt unwrap",
         "out": "Error: wrapping token is not valid or does not exist (HTTP 400)"},
        {"verdict": "TTL expired: the token is dead. The window to intercept is tiny.", "ok": True}]},

    {"title": "The takeaway", "beats": [
        {"prose": "A response-wrapped SecretID is single-use (consumed on unwrap) and short-lived "
                  "(TTL). Together they make the bootstrap credential replay-proof: an attacker who "
                  "intercepts the token has a narrow window to use it, and if the materializer gets "
                  "there first the token is already gone."},
        {"prose": "The deployer needs a privileged token to generate wraps — this is the trust "
                  "anchor. In production that's a CI/CD pipeline with limited scope, an Ansible Tower "
                  "credential, or a cloud identity. The RoleID is the non-secret half; only the "
                  "wrapped SecretID crosses the wire."},
        {"html": '<p class="prose"><strong>Delivery pattern — out of scope.</strong> This demo '
                 'anchors the bootstrap; what <em>consumes</em> the anchored credential (a shim, a '
                 'sidecar, a Cone) is the delivery-pattern family. '
                 'Why &amp; what: <code>enlighten.html</code> · '
                 '<a href="https://github.com/Wave-Engineering/legacy-secrets-adapters">the catalog</a>.</p>'}]},
]
