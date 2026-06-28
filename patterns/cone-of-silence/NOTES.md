# Encryption — Working Notes

> Scratch file for working through encryption questions with Claude.
> Drop a question under "Open Questions" and we'll fill in the answer below it.

---

## Open Questions

- Get cleartext passwords out of the parsed file (`example.json` is a mental model, not the real format).
  - Idea 1: translation layer between sender and process (broker / indirection).
  - Idea 2: encrypt the file, decrypt into a memory drive, keep it encrypted at rest.
- **Blocking decision — RESOLVED:** the process *ingests and uses* the secret → needs plaintext back.
  Hashing is OUT. Encryption / secrets-management is the path; Ideas 1 & 2 are the candidates.
- **HARD CONSTRAINT (new):** the software that *reads* the plaintext secrets will NOT be re-released.
  Its contract is frozen: "read a plaintext file at path P, format F." Every fix must honor it byte-for-byte.
  → Rules out anything requiring the reader to *call* a broker or decrypt (that's a code change).
- **Next decisions (to make the design concrete):** (a) where the reader runs (bare host / container / k8s);
  (b) how the reader is started (can we wrap launch — systemd unit / entrypoint / script?);
  (c) where the decryption key can live (KMS / cloud IAM / TPM / operator passphrase).

### Effect of the "no re-release" constraint — the design converges
Reader is immutable → solution must be **transparent**: keep a plaintext file at path P, but make P
ephemeral and RAM-only.
- **Idea 2 is vindicated and direct:** mount **tmpfs at the reader's exact path**; a wrapper decrypts
  ciphertext into it just-in-time, scrubs after exit. Reader unchanged.
- **Idea 1 survives only as a sidecar that *materializes the file*:** broker/agent fetches the secret
  and *writes the plaintext into the reader's tmpfs path*. Reader still just reads a file.
- They merge: **(optional broker) → materializer (wrapper/sidecar) → tmpfs file → unchanged reader.**

### Named pattern: "secret materialization to file"
Exists specifically for apps you can't modify: Vault Agent `template`, Secrets Manager + init/sidecar,
SOPS-decrypt-in-entrypoint, or FUSE (gocryptfs/EncFS) that decrypts on read.

### Honest residual exposure with tmpfs
Eliminates: plaintext at rest on physical disk, survival across reboot. Narrows window to "while reader runs."
Still exposed in that window: readable by `root` + same mount namespace; swap/`/proc/<pid>/mem`/core dumps.
Mitigations: mode `0400` owned by reader uid; isolate mount (container/pod ns, k8s `emptyDir{medium: Memory}`);
encrypt/disable swap or `mlock`.

### Stronger variant: named pipe (FIFO) at path P
Zero plaintext on any filesystem — writer streams decrypted bytes, reader consumes as a file.
Works ONLY if reader opens once + reads sequentially (no seek/mmap/re-read). tmpfs = safer default;
FIFO = upgrade if access pattern allows.

---

## CONCRETE DESIGN (terrain locked)

**Terrain:** bare-metal RHEL 9.6 · launched as systemd services / kiosk · OpenBao vault available.

### Two materialization layers (keep them separate)
- **Payload:** how the *reader* gets its plaintext file → OpenBao Agent renders secret into tmpfs. Reader unchanged.
- **Bootstrap:** how the *agent* authenticates to OpenBao without a plaintext secret on disk → TPM2-sealed
  AppRole SecretID, unsealed by systemd at start.

### At rest
No plaintext secret on host. Secret lives in OpenBao. Persistent on-host artifacts: bao-agent config,
AppRole **RoleID** (not sensitive alone), **TPM2-sealed SecretID**. Plaintext `example.json` → replaced by template.

### Flow on service start
1. systemd starts `bao-agent.service`; `LoadCredentialEncrypted=` unseals TPM2 SecretID → `$CREDENTIALS_DIRECTORY`
   (tmpfs, 0400, this service only).
2. Agent AppRole login (RoleID + SecretID) → short-lived OpenBao token.
3. Agent renders template → `/run/reader/secrets.json` (tmpfs, 0400, reader uid).
4. `reader.service` (`After=bao-agent.service`) reads that path as always — NO code change.
5. On stop, systemd auto-removes `RuntimeDirectory`; tmpfs → never on disk, gone on reboot.

### systemd features doing the work (both free / native to RHEL 9)
- `RuntimeDirectory=reader` → `/run/reader` on tmpfs, user-locked, **auto-deleted on stop** = scrub-on-exit, no code.
- `LoadCredentialEncrypted=` + `systemd-creds encrypt --with-key=tpm2` → bootstrap secret sealed to THIS box's TPM,
  unsealed into per-service tmpfs at start. Root of trust = silicon; regress stops here.

### Template replacing example.json (illustrative)
```hcl
# rendered → /run/reader/secrets.json
{{ with secret "kv/data/reader" }}
{ "passwd": "{{ .Data.data.passwd }}", "userId": {{ .Data.data.userId }} }
{{ end }}
```

### Hardcoded reader path → bind-mount trick
If reader path is configurable: point it at `/run/reader/secrets.json`.
If hardcoded (e.g. `/etc/app/secrets.json`): bind-mount tmpfs file into the reader's mount namespace —
```ini
[Service]
BindReadOnlyPaths=/run/reader/secrets.json:/etc/app/secrets.json
```
Transparent; no host symlink.

### Caveats for this setup
- **Swap:** `/run` tmpfs pages can swap to disk → use encrypted swap (LUKS) or zram; fold into LUKS-on-TPM root if present.
- **Kiosk:** if reader is a `systemd --user` session → `RuntimeDirectory` lands in `/run/user/<uid>/` (tmpfs). Match uid/mode.
- **Rotation reload:** agent re-renders on rotation; reader only sees it on restart unless it tolerates reload
  (template `command = systemctl try-reload-or-restart reader`). Confirm reader's re-read behavior.

### Open variable (the one unanswered question)
What does the reader authenticate *to*? If DB / OpenBao-supported engine → issue **dynamic short-TTL creds**
instead of a static password → materialized file self-expires; leak is time-boxed. Strictly better than a long-lived secret.

### Static-only fallback (if no rotation + don't want to run the agent)
TPM2-seal the secret itself via `systemd-creds` and have systemd materialize it straight into the reader's
creds tmpfs — no OpenBao Agent. Loses central rotation/audit/least-privilege; only for a truly static secret.

---

## DOWNSTREAM = PostgreSQL  → use OpenBao Database Secrets Engine

The static password disappears entirely; OpenBao becomes the credential authority. Architecture from above
is UNCHANGED — only the secret backend swaps from KV → database engine. Agent template renders OpenBao-issued
creds into the same tmpfs file; reader reads same username/password fields at same path. No reader change.

### Dynamic roles vs static roles — the legacy-reader fork
- **Dynamic roles:** unique NEW Postgres user per lease, short TTL, `DROP`d on expiry. Max security.
  BUT username changes every rotation → breaks a legacy reader's connection pool (new connections fail when
  the leased user is dropped). Fits only if reader re-reads + rebuilds pool, or restarts frequently.
- **Static roles (RECOMMENDED for "can't change the reader"):** OpenBao manages ONE fixed pre-existing PG user
  and rotates only its password on `rotation_period`. Username stable; no human knows the password.

### Unavoidable tension
ANY rotation requires the reader to eventually re-read. On password rotation: existing PG connections survive
(no re-auth of live sessions); next NEW connection needs fresh password. Reader that reads once and holds
forever → rotation eventually breaks a reconnect. No scheme rotates a secret AND never asks the consumer to re-read.

### Resolution: align rotation to restart cadence (kiosk reboots = the re-read)
Each boot: agent rotates static-role password → renders tmpfs file → reader reads fresh creds at startup →
holds connection until next reboot. Set `rotation_period` > reboot interval → reader never sees mid-session rotation.
Rotation + no code change + no reconnect failures.

### Also
- **Rotate OpenBao's own root DB cred** post-setup (`bao write database/rotate-root/...`) → superuser password known to no human.
- **Transport hygiene (orthogonal):** TLS to Postgres (not sniffable in transit) + SCRAM-SHA-256 server auth
  (PG 14+ default → server stores salted verifier, not plaintext). Closes in-transit + server-at-rest to match client-at-rest.

### Finalizing input needed
- Does the reader reconnect / re-read during a run, or open a pool at startup and hold it?
- If kiosk: reboot cadence? → pins `rotation_period` and settles static-vs-dynamic.

---

## OpenBao already mints SSH-CA secrets — de-risks the design
1. **Bootstrap mostly solved** — reuse whatever auth method SSH-CA clients already use (AppRole/cert/OIDC/host certs)
   for the materializer agent instead of inventing one.
2. **Org already operates short-lived issuance** — SSH certs ARE the dynamic-credential model; DB engine is the same
   idea applied to PG, not a new paradigm.
3. **DB engine is incremental** — adding an engine to a running, trusted OpenBao.

## TWO FORKS — secret taxonomy (more than just the PG password to protect)
Test that sorts each secret: *can something mint it on demand, or can you only hold a value someone else issued?*

- **Fork A — Mintable / issued** (no static secret at all; short-lived, auto-expiring):
  - SSH → **SSH-CA (already live)**
  - Postgres → **database engine (proposed)**
  - TLS/x509 → **PKI engine** (if certs in scope)
- **Fork B — Opaque held** (external issuer; nothing on our side can mint/rotate on demand):
  - third-party API keys, vendor/SaaS passwords, license keys, webhook signing secrets
  - Ceiling: **KV → materialize to tmpfs JIT → rotate on vendor terms → audit fetches.** Protect, can't dissolve.

### Unifying insight: both forks ride ONE delivery rail
OpenBao Agent → render to tmpfs → unchanged reader, TPM2/SSH-CA-pattern bootstrap = secret-type-agnostic.
Fork A vs B only changes (a) which engine sits behind the template, (b) rotation cadence.
Build plumbing once; add a template stanza per secret. "More secrets" ≠ more architecture.

### Inventory still needed
- List the "other" secrets → sort each into Fork A (mint) vs Fork B (hold).
- What auth method do current SSH-CA clients use to reach OpenBao? → reuse as agent bootstrap identity.

---

## SINGLE OpenBao INSTANCE (SPOF) — availability analysis
Pivot: ONE OpenBao on the network; stuff must work when it's down. Question: is the only side-effect
"secrets durable until restored"? → **Half true. Depends on WHERE expiry is enforced.**

### Where is expiry enforced? (the load-bearing distinction)
- **OpenBao-enforced** (lease TTL → OpenBao runs `DROP ROLE`): OpenBao down → can't revoke → credential lingers
  and keeps working (catch-up revocation on return). "Durable until restored" = TRUE.
- **Consumer-enforced** (deadline baked into credential, checked by target system): dies on its own clock
  regardless of OpenBao. "Durable until restored" = FALSE.

### Per-type outcome under OpenBao outage
| Secret | Expiry enforced by | Outage effect |
|--------|--------------------|---------------|
| KV / opaque (Fork B) | nothing | keeps working; durable ✓ |
| PG **static** role | nothing (just a password) | keeps working; rotation pauses (mild temp security degr.) ✓ |
| PG **dynamic** role | **Postgres** (`VALID UNTIL`) | new logins rejected at expiry; only-issuer down → can't renew → **HARD OUTAGE** ✗ |
| **SSH cert (live!)** | **target SSH server** (`valid before`) | works until cert expiry, then can't renew → **SSH access fails** ✗ |

### Reframe
Single OpenBao = SPOF at the **renewal/issuance boundary, NOT the use boundary**. Outage breaks anything that
must be re-minted during the window + any reader that restarts during the window. Shorter TTL = tighter coupling
to OpenBao uptime. Short-lived creds trade leak-blast-radius for issuer-dependency; one issuer = that dep is a SPOF.

### Design consequences (the pivot changes 5 things)
1. **Static roles = default on critical path** — now for 2 reasons (legacy reader + outage degrades *security* not *availability*).
   Make OpenBao matter only for rotation, never for staying up.
2. **If using consumer-expiring creds (dynamic DB, SSH certs): validity window ≫ worst-case OpenBao recovery time.**
   Direct security-vs-availability tension; single instance pushes toward longer TTLs. Size SSH cert TTLs for this too.
3. **Auto-unseal is mandatory** — restarted OpenBao comes back SEALED, issues nothing until unsealed. Use **TPM auto-unseal**
   (same TPM as bootstrap anchor) so recovery isn't gated on a human with unseal keys; shrinks outage window → relaxes #2.
4. **Agent persistent encrypted cache** (disk-persisted, TPM-wrappable) → kiosk reboot DURING outage still materializes
   last-known secret. Best for KV + static-role passwords (persisted dynamic cred still bound by `VALID UNTIL`).
5. **Real remedy = HA (integrated Raft, 3 nodes)**, not TTL gymnastics. Removes the issuance SPOF entirely.
   #1–#4 are survival tactics IF single instance is a hard constraint.

### Answer in one line
Static/opaque secrets → durable until restored (rotation merely paused). Issued consumer-expiring secrets
(dynamic DB roles, SSH certs) → NOT durable; expire on own clock, can't renew while OpenBao down. Keep critical
path on static/non-expiring-at-consumer; make OpenBao a dependency for *rotation*, not for *running*.

### Severity gating (PG critical-HA, SSH not)
PG is load-bearing for their critical HA → the one place a single-OpenBao outage can't be tolerated.
SSH non-critical → its existing consumer-expiring exposure is acceptable, no action forced.
Convergence: the outage-proof PG choice (**static roles**) is ALSO the simplest to explain. The scary jargon
part (dynamic short-TTL creds) is exactly what CREATES the availability problem. Audience-friendly == correct.

---

## PRESENTATION — the Cone of Silence (CORE CONCEPT, not the full design)
Audience is NOT a bleeding-edge shop. Lead with the ONE idea; the full OpenBao/dynamic/HA architecture is
"too busy" for the concept pitch. Built a runnable prop: `demonstrate.py` / `cone.py` (+ `README.md`).

**The one line:** the secret is never STORED in the clear, only briefly SHOWN. Disk = ciphertext (permanent,
copyable, in backups). RAM/tmpfs = plaintext (momentary, gone on power-off). tmpfs is the Cone of Silence.

**Sell it by sight (before/after):**
- Today: `grep` the disk → password in cleartext (the problem, in one command).
- After: `grep` the disk → gibberish; plaintext only inside the Cone, briefly, in RAM.
- The reader never changed — still reads "a file"; only what's behind the path changed.

**Stage vs backstage (how to de-busy):**
- ON STAGE (whole concept): encrypted file → decrypt to RAM on use → reader unchanged → Cone disengages.
- BACKSTAGE (1 line, only if asked): key sealed to machine TPM; OpenBao (already run for SSH) hands over + rotates.
- PARKED (don't open with it): dynamic roles, TTLs, lease renewal, auto-unseal, Raft HA = production roadmap.

## Notes & Answers

### The real vulnerability
Plaintext secret **at rest** in a file a process parses. Everyone who can read the file
gets the creds: other processes, backups, container layers, logs, accidental `git add`,
snapshots, core dumps. Every fix is about shrinking *who/what* sees plaintext and *for how long*.

### Decision fork: hash vs. encrypt
- **Verify only** (user supplies password, process checks match) → **hash** with a slow KDF
  (Argon2id / bcrypt / scrypt). One-way: no key to steal. Right answer for account credentials.
  Neither idea below — and better than both for this case.
- **Needs plaintext back** (process uses creds to reach a downstream system) → encryption /
  secrets management. Now Ideas 1 & 2 are the two real options.

> Encryption is reversible by design → always leaves you holding a key (traded "protect the
> secret" for "protect the key"). Hashing is irreversible → no key exists. Reaching for
> encryption when hashing would do is the #1 credential-storage mistake.

### Idea 1 — translation layer (broker / indirection)
File holds only a *reference* (key name / path / ARN); process asks a broker (Vault, AWS
Secrets Manager, SOPS+KMS, local agent over unix socket) for the real value at runtime.
- + Central rotation, audit trail, least-privilege, plaintext only briefly in memory, never on disk.
- − Operational dependency (broker must be up); process needs to authenticate *to* the broker.

### Idea 2 — encrypt at rest + decrypt into tmpfs (memory drive)
Envelope encryption: ciphertext on disk, decrypt into a RAM-backed mount so plaintext never
touches the block device and vanishes on reboot.
- + Simpler, no broker, plaintext never persisted to disk.
- − **Key custody is the whole game** — key beside the file = key under the mat. Must come from
  KMS / TPM / orchestrator-injected env / operator passphrase.
- − **tmpfs ≠ vault**: pages can swap to disk under memory pressure (encrypt/disable swap or
  `mlock`); plaintext in RAM still readable by root, `ptrace`, `/proc/<pid>/mem`, core dumps.
  Shrinks the *persistence* surface, not the *runtime* surface.

### Unifying principle
Can't make a secret from nothing. Idea 1 needs broker auth; Idea 2 needs a decryption key.
Both push the secret *down* to a root of trust the file-thief lacks — IAM role, mTLS/SPIFFE
identity, TPM, HSM. The regress stops at silicon.

### Recommendation
- Verifiable account passwords → **hash (Argon2id)**, don't encrypt.
- Process needs plaintext → **Idea 1 (broker) is stronger** (rotation/audit/least-privilege);
  **Idea 2 is the fallback** when no broker is available *and* the key is anchored to KMS/TPM/env.
  They compose: broker hands secrets into a tmpfs scratch space.
- **Hygiene:** the three sample values (`1234567`, `P455wd`, `Ch@ng3m3`) are compromised by being
  cleartext — rotate any real equivalents; never commit this file as-is.

## Glossary

| Term | Meaning |
|------|---------|
| AEAD | Authenticated Encryption with Associated Data — encrypts *and* authenticates in one pass (e.g. AES-GCM, ChaCha20-Poly1305). |
| KDF  | Key Derivation Function — turns a password/secret into a key (Argon2id, scrypt, PBKDF2, HKDF). |
| IV / Nonce | Number-used-once — randomizes encryption so identical plaintexts differ; must never repeat under the same key. |
| KEM / DEM | Key/Data Encapsulation Mechanism — the hybrid-encryption split: public-key wraps a symmetric key, symmetric key encrypts the data. |

## References

-
