"""walkthrough.py — the TPM-Sealed Bootstrap slide deck as DATA.

`tools/build_deck.py` renders `SLIDES` -> a self-contained, deterministic `deck.html`.
The frozen `out` strings are representative output — frozen so the deck is byte-identical
on every machine. The interactive TUI (`demonstrate.py`) runs the real commands.

Beats (same vocabulary as the deck renderer):
  {"title", "tagline", "kicker"}   the cover slide
  {"say": str}                     narration
  {"prose": str}                   body text
  {"cmd": str, "out": str}         a command shown at the demo prompt + its (frozen) output
  {"verdict": str, "ok": bool}     the capping success/failure line
  {"html": str}                    raw html (closing links)
"""

DEMO_PROMPT = "[you@host tpm-sealed-bootstrap]$ "

SLIDES = [
    {"title": None, "beats": [
        {"title": "TPM-Sealed Bootstrap",
         "tagline": "seal the materializer's credential to silicon — the regress ends at the hardware",
         "kicker": "legacy-secrets-adapters · a walkthrough"}]},

    {"title": "The bootstrap problem", "beats": [
        {"prose": "A materializer needs a credential to authenticate to its key source (e.g. OpenBao). "
                  "But where does THAT credential live? If it's a file, we're back to the same problem. "
                  "If it's another vault, who authenticates to THAT vault? Turtles all the way down."},
        {"prose": "The TPM ends the regress: seal the bootstrap credential to the machine's hardware "
                  "root of trust. Only THIS machine, in THIS boot state, can unseal it. The secret "
                  "never exists in cleartext on disk — it goes from silicon to RAM to the wire."}]},

    {"title": "Start the software TPM", "beats": [
        {"say": "For the demo we use swtpm (a software TPM2 emulator). In production this is the\n"
                "physical TPM2 chip on the motherboard — /dev/tpmrm0."},
        {"cmd": "swtpm socket --tpmstate dir=swtpm-state --tpm2 --ctrl type=unixio,path=swtpm-state/swtpm-sock --flags not-need-init,startup-clear &",
         "out": "[swtpm started, PID 12345]"}]},

    {"title": "Seal the credential to the TPM", "beats": [
        {"say": "Seal our bootstrap secret (here: an obvious fake) to the TPM's current PCR state.\n"
                "The output is an opaque blob — ciphertext bound to this machine's measurements."},
        {"cmd": 'echo -n "S3cr3t-Pg-Pass" | systemd-creds encrypt --with-key=tpm2 --name=bao-token - run/bao-token.cred',
         "out": ""},
        {"cmd": "ls -la run/bao-token.cred",
         "out": "-rw------- 1 you you 456 Jan  1 09:00 run/bao-token.cred"},
        {"say": "Is the plaintext in the blob? It must not be:"},
        {"cmd": "grep -c 'S3cr3t-Pg-Pass' run/bao-token.cred || echo 'not found (good)'",
         "out": "not found (good)"},
        {"verdict": "Sealed. The credential is ciphertext on disk, bound to silicon.", "ok": True}]},

    {"title": "Unseal via the TPM", "beats": [
        {"say": "systemd-creds decrypt reverses the seal — but ONLY if the TPM's PCR state matches.\n"
                "This is what systemd does at service start with LoadCredentialEncrypted=."},
        {"cmd": "systemd-creds decrypt --name=bao-token run/bao-token.cred -",
         "out": "S3cr3t-Pg-Pass"},
        {"verdict": "Unsealed. In production this lands in $CREDENTIALS_DIRECTORY (tmpfs, 0400).", "ok": True}]},

    {"title": "Materializer authenticates", "beats": [
        {"say": "The materializer reads the unsealed credential from $CREDENTIALS_DIRECTORY and\n"
                "authenticates to OpenBao. The credential went: TPM -> RAM -> network. Never disk."},
        {"cmd": "CREDENTIALS_DIRECTORY=/run/credentials/tpm-demo BAO_ADDR=http://127.0.0.1:58300 python3 materializer.py",
         "out": "[materializer] read credential 'bao-token' from $CREDENTIALS_DIRECTORY (14 chars, never printed)\n"
                "[materializer] authenticated to OpenBao as 'token'\n"
                "[materializer] bootstrap complete — credential never touched disk"},
        {"verdict": "Bootstrap complete. The materializer is authenticated without a stored secret.", "ok": True}]},

    {"title": "Tamper test — PCR-extend breaks unseal", "beats": [
        {"say": "The TPM binding means: change the machine's boot measurements and the credential\n"
                "becomes irrecoverable. Simulate by restarting swtpm with fresh state:"},
        {"cmd": "# restart swtpm with new state (simulates different PCR values)",
         "out": "[swtpm restarted with fresh measurements]"},
        {"cmd": "systemd-creds decrypt --name=bao-token run/bao-token.cred -",
         "out": "Failed to decrypt credential: TPM2 policy authorization failed"},
        {"verdict": "Unseal FAILED. A tampered machine cannot recover the bootstrap credential.", "ok": True}]},

    {"title": "The takeaway", "beats": [
        {"prose": "The bootstrap regress ends at silicon. The materializer's credential is sealed to "
                  "the TPM — it never exists in cleartext on disk, it can only be recovered by THIS "
                  "machine in THIS boot state, and a tamper (firmware change, different machine, "
                  "boot attack) makes it irrecoverable."},
        {"prose": "In production: systemd's LoadCredentialEncrypted= unseals at service start into a "
                  "per-service tmpfs ($CREDENTIALS_DIRECTORY, mode 0400). The materializer reads it, "
                  "authenticates, and the credential lives only in RAM for the duration of the call."},
        {"prose": "PCR brittleness is real — a kernel update changes measurements and breaks unseal. "
                  "The reseal ceremony (orchestrated re-sealing after a known-good update) is the "
                  "operational cost. Pair with Cone of Silence for the delivery side."},
        {"html": '<p class="prose"><strong>Delivery pattern -- out of scope.</strong> This demo '
                 'anchors the bootstrap secret (the materializer\'s token). What <em>consumes</em> '
                 'the anchored credential -- a delivery pattern that materializes the secret to an '
                 'unchanged app -- is an orthogonal concern (see the delivery-pattern family). '
                 'Why &amp; what: <code>enlighten.html</code> &middot; '
                 '<a href="https://github.com/Wave-Engineering/legacy-secrets-adapters">the catalog</a>.</p>'}]},
]
