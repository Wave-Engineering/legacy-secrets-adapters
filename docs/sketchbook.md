# Pattern Sketchbook — design intentions for the wave campaign

This document captures the **mechanism, decision-tree leaf, demo plan, and honest tradeoffs**
for each planned pattern. It serves as the spec source when filing wave-campaign sub-issues —
so each pattern-building agent has a clear brief rather than improvising from scratch.

The sketchbook covers both axes: **delivery & lifecycle** and **bootstrap-secret**.

---

## Delivery & lifecycle patterns

### broker-sidecar

| Field | Value |
|-------|-------|
| **Axis** | Delivery & lifecycle |
| **Essence** | Materialize a secret from OpenBao/Vault into a file for an unchanged reader, with audit and templating |
| **Decision-tree leaf** | Can you change the reader? → **Yes** (you can wrap its launch / sidecar it) |

**Mechanism.** A sidecar process (or systemd unit wrapping the reader's launch) authenticates to
OpenBao/Vault, fetches the secret, renders it through a template into a file at the reader's
expected path, and manages its lifecycle (rotation watch, re-render on lease renewal, revocation on
stop). The reader never knows a broker exists — it reads its file as always.

This is the `dynamic-credential-shim` **generalized**: the shim handles only rotating Postgres
credentials behind a fixed file; the broker handles *any* secret type with templating and audit.

**Demo plan — what a skeptic sees.**
1. Broker starts → fetches a KV secret from a dev-mode OpenBao → writes it to a file.
2. Legacy reader reads the file, prints the secret value — proves delivery works.
3. Secret is rotated in OpenBao → broker detects and re-renders the file.
4. Legacy reader reads again → sees the *new* value (proves lifecycle/rotation).
5. `grep` the disk: only the broker's rendered file exists (at a controlled path); no stale copies.

**Runtime dependencies:** Docker + OpenBao (same family as dynamic-credential-shim). Python + Jinja2
(or stdlib `string.Template` to stay low-dep). **Runs here.**

**Demo-runnability tier:** ✅ runs in this environment (Docker + OpenBao proven by the shim).

**Honest tradeoffs / residual exposure.**
- **Operational dependency on the broker.** If the broker dies, the file goes stale (vs.
  cone-of-silence which is transparent once engaged). Mitigated: systemd restart + staleness alarm.
- **Plaintext on disk** (at the rendered path). Compose with cone-of-silence (tmpfs target) to keep
  it RAM-only — but the broker alone doesn't guarantee that.
- **Bootstrap secret is out of scope.** The broker must authenticate to OpenBao — how it gets *its
  own* credential is the bootstrap-secret axis.

**Axis callout:** `## Bootstrap secret — out of scope` (delivery pattern convention).

---

### fifo-stream

| Field | Value |
|-------|-------|
| **Axis** | Delivery & lifecycle |
| **Essence** | Named pipe (zero disk) for read-once sequential readers |
| **Decision-tree leaf** | Can you change the reader? → **No** (transparent). Reader reads the path *once, sequentially* (no seek/mmap) |

**Mechanism.** Replace the file at the reader's expected path with a POSIX named pipe (`mkfifo`). A
writer process decrypts the secret and streams it into the pipe; the reader opens and reads it as if
it were a normal file. The secret **never touches any filesystem** — not even tmpfs. It exists only
momentarily in kernel pipe buffers.

This is the **strongest** transparent variant for readers with a compatible access pattern (strictly
stronger than cone-of-silence's tmpfs, which leaves the plaintext in RAM until disengaged).

**Demo plan — what a skeptic sees.**
1. Show the "file" is actually a named pipe (`stat` / `ls -l`).
2. Writer feeds the decrypted secret into the pipe (blocks until reader opens).
3. Legacy reader opens the path, reads the secret, prints it — proves delivery.
4. `grep` / `find` the entire filesystem: **zero** plaintext residue anywhere (not on disk, not in
   tmpfs, not in `/proc`). The secret existed only in the pipe buffer during the read syscall.
5. Second `cat` of the path blocks (pipe is empty) — proves read-once semantics.

**Runtime dependencies:** Python stdlib only (`os.mkfifo`, `threading`). No Docker, no external
services. **Runs anywhere with POSIX.**

**Demo-runnability tier:** ✅ runs in this environment (stdlib, no privileges needed).

**Honest tradeoffs / residual exposure.**
- **Strictly sequential, read-once.** If the reader seeks, mmaps, re-reads, or opens the path a
  second time → undefined behavior / hang. This pattern is ONLY valid when the access pattern is
  confirmed sequential.
- **Writer must be running when reader opens.** Timing coordination needed (writer blocks on open
  until reader connects, which is fine; but reader blocks if writer isn't ready).
- **No persistence.** If the reader crashes mid-read, the secret is gone — the writer must re-feed.
- **Bootstrap secret is out of scope.** The writer must decrypt from *somewhere* — where it gets the
  key is the bootstrap axis.

**Axis callout:** `## Bootstrap secret — out of scope` (delivery pattern convention).

---

### fuse-decrypt

| Field | Value |
|-------|-------|
| **Axis** | Delivery & lifecycle |
| **Essence** | FUSE filesystem that decrypts on read (and handles writes) |
| **Decision-tree leaf** | Can you change the reader? → **No** (transparent). Reader does **arbitrary reads/writes** (seek, mmap, partial reads, rewrites) |

**Mechanism.** A FUSE filesystem mounts at the reader's expected path (or parent directory).
Ciphertext lives on the real filesystem; the FUSE layer decrypts on `read()` and encrypts on
`write()` transparently. The reader sees plaintext via the mount; the underlying storage holds only
ciphertext. Handles arbitrary POSIX file operations.

This is the "full power" transparent variant — handles access patterns that neither cone-of-silence
(tmpfs, but requires engage/disengage lifecycle) nor fifo-stream (sequential-only) can serve.

**Demo plan — what a skeptic sees.**
1. Show the backing file is ciphertext (`xxd` / `file` on the underlying storage).
2. Mount the FUSE layer. Reader opens the path through the mount → sees plaintext.
3. Reader writes modified content → stored as ciphertext on disk.
4. Unmount. `cat` the backing file directly → ciphertext only.
5. Remount, re-read → plaintext restored. Proves round-trip encrypt/decrypt.

**Runtime dependencies:** `/dev/fuse` (kernel module), `libfuse3`, Python FUSE bindings (`pyfuse3`
or `fusepy`). **Environment-sensitive** — needs FUSE kernel support and may not work in all
containers/VMs.

**Demo-runnability tier:** ⚠️ environment-sensitive. Needs `/dev/fuse` + unprivileged FUSE mounts
(or root). May require a validate.sh gating check similar to the Docker gate.

**Honest tradeoffs / residual exposure.**
- **Complexity.** FUSE is a significantly more complex mechanism than tmpfs or named pipes — more
  moving parts, harder to debug, more kernel interaction surface.
- **Performance.** Every I/O syscall traverses userspace↔kernel via FUSE — measurably slower than
  native filesystem access. Acceptable for config files; problematic for high-throughput data.
- **Key in process memory.** The FUSE daemon holds the decryption key in memory for the mount's
  lifetime — same exposure as cone-of-silence's tmpfs, but longer-lived (mount stays up vs.
  engage/disengage window).
- **Availability.** If the FUSE daemon crashes, the mount becomes stale (EIO on access). Must
  supervise (systemd, auto-restart).
- **Bootstrap secret is out of scope.** Where the FUSE daemon gets its decryption key is the
  bootstrap axis.

**Axis callout:** `## Bootstrap secret — out of scope` (delivery pattern convention).

---

## Bootstrap-secret patterns

### tpm-sealed-bootstrap

| Field | Value |
|-------|-------|
| **Axis** | Bootstrap-secret |
| **Essence** | Seal the materializer's bootstrap credential to the machine's TPM — turtles end at silicon |
| **Decision-tree leaf** | The orthogonal axis: how does the materializer authenticate to its key source without a stored secret? → **Hardware root of trust (TPM)** |

**Mechanism.** The bootstrap credential (e.g. an AppRole SecretID, a Vault token, a symmetric key)
is **sealed to the machine's TPM2 PCR state** via `systemd-creds encrypt`. At service start,
`systemd` unseals it into `$CREDENTIALS_DIRECTORY` (a tmpfs, mode 0400, invisible to other
processes). The materializer reads the credential from there, authenticates to its key source
(OpenBao/Vault/KMS), fetches the runtime secret, and delivers it to the app.

The regress ends at silicon: a file-thief who copies the disk gets *sealed ciphertext* that only
this machine's TPM can unseal — and only under the expected boot-measurement state.

**Demo plan — what a skeptic sees.**
1. Show `systemd-creds encrypt` sealing a dev credential to a simulated TPM (`swtpm`).
2. Show the sealed blob on disk — `xxd` proves it's opaque ciphertext.
3. Start the service unit → systemd unseals → materializer authenticates to dev-mode OpenBao.
4. `cat /proc/<pid>/environ` + `ls $CREDENTIALS_DIRECTORY` → credential is in tmpfs, not on disk.
5. Copy the sealed blob to a different machine (or clear PCR state) → unseal **fails**. Proves
   hardware-binding.

**Runtime dependencies:** `swtpm` (software TPM emulator), `systemd` (≥ 250 for
`LoadCredentialEncrypted=`), OpenBao (for the auth target). Python for the materializer script.
**Environment-sensitive** — needs systemd + swtpm (or a real TPM).

**Demo-runnability tier:** ⚠️ environment-sensitive. `swtpm` is installable (`dnf install swtpm`)
but the demo needs systemd service management (may not work inside containers). Gate on
`systemctl --version` + `swtpm` presence.

**Honest tradeoffs / residual exposure.**
- **Hardware-bound.** The sealed credential cannot be migrated to another machine without
  re-sealing — intentional (security property) but operationally constraining for fleet scaling.
- **TPM availability.** Not all machines have a TPM2 (VMs may lack vTPM; older hardware; some cloud
  instances). The demo uses `swtpm` to prove the flow without real hardware.
- **PCR brittleness.** If the boot chain changes (kernel update, initrd rebuild, firmware update),
  the PCR measurements change → unseal fails → service can't start until re-sealed. Operational
  procedure needed for planned updates.
- **systemd coupling.** The unsealing mechanism is specific to `systemd-creds` / `LoadCredentialEncrypted=`.
  Not portable to non-systemd init systems (rare in modern Linux servers, but worth stating).
- **Still trusts the key source.** The TPM seals the *bootstrap* — the runtime secret still depends
  on OpenBao/Vault being available and honest. TPM eliminates the stored-secret problem, not the
  operational-trust problem.

**Axis callout:** `## Delivery pattern — out of scope` (bootstrap pattern convention).

---

## Candidates (lighter sketch — not yet committed to the catalog table)

### approle-response-wrapping

| Field | Value |
|-------|-------|
| **Axis** | Bootstrap-secret |
| **Essence** | Use OpenBao/Vault AppRole response-wrapping to deliver the SecretID without exposing it in transit or at rest |

**Intent.** Instead of pre-placing a SecretID on the machine (which is a stored secret — the very
thing we're trying to eliminate), use response-wrapping: the deployer requests a wrapped token that
can be unwrapped *exactly once* by the target machine. The wrapping token is short-lived and
single-use — even if intercepted, it's already consumed or expired.

**Decision-tree position.** Orthogonal bootstrap axis — answers "how does the materializer get its
*first* credential?" for environments where a TPM is unavailable but a trusted deployment pipeline
(CI/CD, orchestrator) can deliver a one-time token.

**Open questions before committing.**
- Does the demo need a real deployment pipeline (Ansible/Nomad/etc.) to show the wrapping flow, or
  can a simple two-terminal demo suffice?
- How does this compose with `tpm-sealed-bootstrap`? (They're alternatives, not layers — pick one.)

---

### cloud-instance-identity

| Field | Value |
|-------|-------|
| **Axis** | Bootstrap-secret |
| **Essence** | Anchor bootstrap to the cloud provider's instance metadata (AWS IAM instance profile, GCP service account, Azure managed identity) |

**Intent.** In cloud environments, the machine already *has* a hardware-backed identity issued by
the provider (an instance profile, a service account token refreshed via the metadata service). Use
this as the bootstrap credential: the materializer calls the metadata endpoint, gets a short-lived
token, and uses it to authenticate to the key source (Vault's AWS/GCP/Azure auth methods).

**Decision-tree position.** Orthogonal bootstrap axis — the cloud-native alternative to TPM. Fits
when the workload runs on a cloud instance with an assigned identity (most modern cloud deploys).

**Open questions before committing.**
- The demo needs a cloud provider (or a convincing mock metadata service). Is a LocalStack / mock
  approach honest enough, or does it need real cloud creds (which contradicts "no real secrets")?
- How many providers do we cover? One (AWS) as the exemplar, or a provider-agnostic abstraction?
- Does this warrant its own pattern, or is it a "variant" appendix inside `tpm-sealed-bootstrap`?
