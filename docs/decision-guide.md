# Which pattern fits? — a decision guide

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
  **dynamic issuance** so a leak is self-limiting. → `dynamic-credential-shim` (planned),
  `tpm-sealed-bootstrap` (planned).
- **Opaque / held** — a value issued by an external party you can't mint or rotate on
  demand (a third-party API key, a vendor password). You can only *protect the held
  value*. → the materialization patterns below.

## 3. Can you change the reader?

- **No (the common, hard case)** — the app reads a file at a fixed path and won't be
  re-released. The fix must be **transparent**: change what's *behind* the path, not the
  app.
  - Secret fits in a file read once → **[`cone-of-silence`](../patterns/cone-of-silence/)**
    (encrypt at rest, decrypt only into a RAM/tmpfs file at the app's path). ✅ available
  - Reader reads the path *once, sequentially* (no seek/mmap) → `fifo-stream` (planned) —
    a named pipe, zero plaintext on any filesystem.
  - Reader does arbitrary reads/writes → `fuse-decrypt` (planned) — a FUSE filesystem that
    encrypts on write, decrypts on read.
- **Yes (you can wrap its launch / sidecar it)** — a broker can hand the secret over.
  → `broker-sidecar` (planned): fetch from OpenBao/Vault and materialize for the reader,
  with rotation and audit.

## Cross-cutting: where does the key (or broker identity) live?

Every pattern eventually bottoms out at a root of trust the file-thief can't reach —
a cloud KMS/IAM role, an mTLS/SPIFFE identity, a **TPM**, an HSM. You can't make a secret
from nothing; you can only anchor it to hardware. `tpm-sealed-bootstrap` (planned) covers
the bootstrap-identity problem directly.
