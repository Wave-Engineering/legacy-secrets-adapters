"""walkthrough.py — the cloud-instance-identity slide deck as DATA.

`tools/build_deck.py` renders `SLIDES` -> a self-contained, deterministic `deck.html`.
The frozen `out` strings are REPRESENTATIVE output from a live run, with values frozen
so the deck is byte-identical on every machine. The interactive TUI (`demonstrate.py`)
runs the same commands for real against the local container stack.

Beats (same vocabulary as the deck renderer):
  {"title", "tagline", "kicker"}   the cover slide
  {"say": str}                     narration
  {"prose": str}                   body text
  {"cmd": str, "out": str}         a command shown at the demo prompt + its (frozen) output
  {"verdict": str, "ok": bool}     the capping success/failure line
  {"html": str}                    raw html (closing links)
"""

DEMO_PROMPT = "[you@instance cloud-instance-identity]$ "

SLIDES = [
    {"title": None, "beats": [
        {"title": "Cloud Instance Identity",
         "tagline": "the machine already has an identity — use it as the bootstrap credential",
         "kicker": "legacy-secrets-adapters - a walkthrough"}]},

    {"title": "The problem", "beats": [
        {"prose": "Every secret-delivery pattern (Cone of Silence, Dynamic Credential Shim) needs a "
                  "BOOTSTRAP credential to authenticate to its key source. But where does THAT credential "
                  "come from? If you store it on disk, you've just moved the problem. The turtles-to-silicon "
                  "regress has to end somewhere."},
        {"prose": "On a cloud instance, it already has: the machine's identity IS the credential. "
                  "The cloud provider's control plane assigned it an IAM role when it launched. "
                  "The metadata endpoint hands out short-lived tokens that prove 'I am this instance'. "
                  "No stored secret required."}]},

    {"title": "The IMDSv2 flow", "beats": [
        {"say": "AWS Instance Metadata Service v2 uses a two-step flow to prevent SSRF attacks:\n"
                "Step 1: PUT to get a session token (requires the TTL header).\n"
                "Step 2: GET with that token to retrieve credentials."},
        {"cmd": "curl -s -X PUT -H 'X-aws-ec2-metadata-token-ttl-seconds: 300' "
                "http://169.254.169.254/latest/api/token",
         "out": "a4b2c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7"},
        {"cmd": "curl -s -H 'X-aws-ec2-metadata-token: <token>' "
                "http://169.254.169.254/latest/meta-data/iam/security-credentials/demo-instance-role",
         "out": '{\n'
                '  "Code": "Success",\n'
                '  "AccessKeyId": "AKIAIOSFODNN7EXAMPLE",\n'
                '  "SecretAccessKey": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",\n'
                '  "Token": "FwoGZXIvYXdzE-session-token-0001",\n'
                '  "Expiration": "2026-01-01T10:00:00Z"\n'
                '}'},
        {"say": "The session token and the STS credentials are both short-lived.\n"
                "No stored secret — just a conversation with the hypervisor."}]},

    {"title": "Authenticate to OpenBao", "beats": [
        {"say": "The materializer uses the AWS credentials to authenticate to OpenBao\n"
                "via the AWS auth method. OpenBao verifies the identity with STS and\n"
                "returns a Vault token scoped to the instance's policy."},
        {"cmd": "./materializer.py",
         "out": "[materializer] requesting IMDSv2 session token ...\n"
                "[materializer] got session token; fetching instance credentials ...\n"
                "[materializer] got credentials for role (AccessKeyId=AKIAIОСF...)\n"
                "[materializer] authenticating to OpenBao via AWS auth method ...\n"
                "[materializer] authenticated (token=hvs.CAES...)\n"
                "[materializer] reading secret from secret/data/demo/db-password ...\n"
                "[materializer] got secret; writing to run/secret.json ...\n"
                "[materializer] done - secret materialized to run/secret.json (mode 0600)"},
        {"verdict": "Authenticated and fetched secret — no stored bootstrap credential used.", "ok": True}]},

    {"title": "No secrets on disk", "beats": [
        {"say": "The only file written is the delivery output (the secret itself).\n"
                "No Vault tokens, no AWS credentials, no session tokens on disk."},
        {"cmd": "cat run/secret.json",
         "out": '{\n'
                '  "password": "S3cr3t-Pg-Pass",\n'
                '  "username": "app_user"\n'
                '}'},
        {"cmd": "grep -r 'dev-only-root-token\\|hvs\\.' run/ || echo '(none found)'",
         "out": "(none found)"},
        {"verdict": "Only the delivery payload is on disk. Auth tokens stayed in memory.", "ok": True}]},

    {"title": "Token rotation is built-in", "beats": [
        {"say": "Each call to the metadata endpoint returns fresh, short-lived credentials.\n"
                "The cloud control plane handles rotation — no cron job, no lease renewal."},
        {"cmd": "# call 1",
         "out": 'Token: "FwoGZXIvYXdzE-session-token-0001"'},
        {"cmd": "# call 2",
         "out": 'Token: "FwoGZXIvYXdzE-session-token-0002"'},
        {"verdict": "Fresh credentials every time. Rotation is the cloud's native model.", "ok": True}]},

    {"title": "The takeaway", "beats": [
        {"prose": "The bootstrap-secret problem — 'what authenticates the authenticator?' — ends at "
                  "a root of trust the file-thief cannot reach. On a cloud instance, that root is the "
                  "provider's control plane: the machine's identity IS the credential, assigned at launch, "
                  "unreachable from outside."},
        {"prose": "No file to steal, no token to rotate, no secret to seal. The instance metadata "
                  "endpoint is the trust anchor — backed by the hypervisor, scoped to this machine, "
                  "short-lived by design."},
        {"html": '<p class="prose"><strong>Delivery pattern - out of scope.</strong> This demo anchors '
                 'the bootstrap credential (cloud instance identity); what <em>consumes</em> it - a delivery '
                 'pattern that materializes the secret to an unchanged app - is an orthogonal concern '
                 '(the delivery-pattern family). Why &amp; what: <code>enlighten.html</code> &middot; '
                 '<a href="https://github.com/Wave-Engineering/legacy-secrets-adapters">the catalog</a>.</p>'}]},
]
