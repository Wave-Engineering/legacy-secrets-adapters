# Which pattern fits? — a decision guide

> **Prefer the live advisor.** This static tree covers the basics, but real problems
> are messier than three questions. The **Secrets Advisor** (`skills/secrets-advisor/`)
> holds the full catalog in working memory and narrows your problem through dialogue —
> constraints, compositions, Defence in Depth, honest tradeoffs. Use it when your
> situation doesn't fit neatly into the branches below.

Before reaching for any adapter, walk three questions. They narrow the space fast,
and the wrong turn early (encrypting something you should have hashed, or building a
broker for a secret that should be minted on demand) wastes the most effort.

## 1. Does the app need the *plaintext*, or only to *verify* a value?

- **Verify only** (the app checks a password a user supplies) → **hash it** with a slow
  KDF (Argon2id, scrypt, bcrypt). One-way: there's no key to steal. None of these
  patterns apply — and reaching for encryption here is the most common mistake.
- **Recover the plaintext** (the app *uses* the secret — connects to a DB, calls an API) →
  continue. This is what the catalog is for.

## 2. Can the secret be *minted on demand*, or only *held*?

- **Mintable / issued** — a credential authority can generate it short-lived and
  auto-expiring (a database password via OpenBao, an SSH cert, an x509 cert). Prefer
  **dynamic issuance** so a leak is self-limiting. → **[`dynamic-credential-shim`](../delivery-pattern-demos/dynamic-credential-shim/)**
  (`tpm-sealed-bootstrap` is a *bootstrap* pattern — a different axis; see below.)
- **Opaque / held** — a value issued by an external party you can't mint or rotate on
  demand (a third-party API key, a vendor password). You can only *protect the held
  value*. → the materialization patterns below.

## 3. Can you change the reader?

- **No (the common, hard case)** — the app reads a file at a fixed path and won't be
  re-released. The fix must be **transparent**: change what's *behind* the path, not the
  app.
  - Secret fits in a file read once → **[`cone-of-silence`](../delivery-pattern-demos/cone-of-silence/)**
    (encrypt at rest, decrypt only into a RAM/tmpfs file at the app's path).
  - Reader reads the path *once, sequentially* (no seek/mmap) → **[`fifo-stream`](../delivery-pattern-demos/fifo-stream/)** —
    a named pipe, zero plaintext on any filesystem.
  - Reader does arbitrary reads/writes → **[`fuse-decrypt`](../delivery-pattern-demos/fuse-decrypt/)** — a FUSE filesystem that
    encrypts on write, decrypts on read.
- **Yes (you can wrap its launch / sidecar it)** — a broker can hand the secret over.
  → **[`broker-sidecar`](../delivery-pattern-demos/broker-sidecar/)**: fetch from OpenBao/Vault and materialize for the reader,
  with rotation and audit.

## The other axis: the bootstrap secret (orthogonal)

Every delivery pattern bottoms out at the same question: *how does the materializer/broker
authenticate to its **own** key source without a stored secret?* — the turtles-to-silicon regress.
It ends at a root of trust the file-thief can't reach: a cloud KMS/IAM role, an mTLS/SPIFFE
identity, a **TPM**, an HSM. You can't make a secret from nothing; you can only anchor it to hardware.

This is **orthogonal** to delivery/lifecycle, so the catalog treats it as a separate axis. **Inside
each delivery demo it is deliberately out of scope** — the demo hardcodes its bootstrap secret
obviously and says so, rather than half-solving key custody and implying the pattern handles it. The
bootstrap-secret family addresses it head-on:

- **[`tpm-sealed-bootstrap`](../bootstrap-pattern-demos/tpm-sealed-bootstrap/)** — seal the anchor to the machine's TPM.
- **[`approle-response-wrapping`](../bootstrap-pattern-demos/approle-response-wrapping/)** — single-use wrapped token delivered by Ansible/CD.
- **[`cloud-instance-identity`](../bootstrap-pattern-demos/cloud-instance-identity/)** — the machine's IAM role IS the credential (EC2/GCE/Azure).
