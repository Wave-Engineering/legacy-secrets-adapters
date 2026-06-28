# Cone of Silence

*the Cone of Silence — a low-effort, RAM-only zone your secret never leaves. Give a legacy app its plaintext secret without ever writing it to disk.*

## Context — when you're here

- A legacy application reads a secret from a **plaintext file** at a fixed path (e.g. `/etc/secrets.json`).
- You **cannot change the application** — it will not be re-released.
- The process genuinely **needs the plaintext** (it *uses* the secret — e.g. to connect to Postgres),
  so hashing is off the table. This is recover-the-value territory, not verify-a-value.

## Forces

- Plaintext-at-rest is the vulnerability: backups, container image layers, `grep`, a stray `git add`, a stolen disk.
- The reader's contract is frozen: *"open a file at path P, in format F."*
- Therefore any fix must be **transparent to the reader** — it can't change how the app obtains its secret.

## Solution

Keep the secret **encrypted on disk**. At runtime, decrypt it into a **RAM-backed (tmpfs) file** and point the
reader's path at it — directly, or via a **symlink** when the path is hard-coded. The plaintext lives only in RAM,
only while needed; the disk holds ciphertext; the app is untouched.

## How it works

```
  secrets.json.enc ──decrypt (key: TPM / OpenBao)──▶  /run/cone/secrets.json   ◀── legacy app opens
   (on disk: ciphertext)                              (tmpfs: the "Cone")           /etc/secrets.json
                                                                                    (symlink → the Cone)
```

Same syscall, same path the app always used — only what's *behind* the path changed. See **`enlighten.html`**
for the illustrated version (side-by-side before/after diagrams).

## Run the demo

```bash
./demonstrate.py     # interactive: engage/disengage the Cone, read the secret, hunt the disk, explore
./cone.py demo       # quick non-interactive walk of the whole arc
```

Requirements: `python3` + the `cryptography` package (`dnf install python3-cryptography` or
`python3 -m pip install cryptography`). `bat` is optional — it syntax-highlights the JSON in the walkthrough.
Open `enlighten.html` in a browser for the illustrated write-up.

| File | Role |
|------|------|
| `demonstrate.py` | interactive control plane — the *experience* (menu, walkthroughs, Explorer) |
| `cone.py` | the Cone engine — `init` / `engage` / `disengage` / `run` / `prove` / `demo` |
| `legacy_reader.py` | the app we cannot change (reads `--config` / `CONFIG_PATH` / its hard-coded path) |
| `enlighten.html` | illustrated write-up — diagrams, *Transparency in Secrecy*, *what about writes* |
| `NOTES.md` | production deep-dive (OpenBao, static/dynamic roles, TPM, single-instance availability) |
| `BACKLOG.md` | demo polish backlog, incl. the deferred JSON-driven generalization |

## Tradeoffs / residual exposure

RAM is not a vault. A tmpfs plaintext is still readable by `root`, via `ptrace` / `/proc/<pid>/mem`, by a process
sharing its mount namespace, and can leak to swap or a core dump. The honest goal isn't "never in cleartext
anywhere" — it's *no plaintext at rest on disk*, *materialized just-in-time*, *least-privilege*, *audited*.
`enlighten.html` → **Transparency in Secrecy** documents eight layered mitigations (temporal mounting, dedicated
user, systemd sandboxing, mount namespaces, no-swap/`mlock`, `ptrace` restriction, core-dump disable, SELinux/MAC).

## Production hardening

- The Cone is a per-service tmpfs at `/run/<service>` (systemd `RuntimeDirectory`; the directory locked to 0700 via `RuntimeDirectoryMode`, the secret file mode 0400, app-owned, auto-removed on stop).
- The decryption key **never touches disk** — sealed to the machine's TPM, or handed over by OpenBao.
- **Postgres specifically:** replace the static password with an OpenBao **static role** (rotated password, stable
  username — friendliest to a legacy connection pool) or a dynamic role. The static-vs-dynamic decision and the
  single-OpenBao availability caveats are worked through in `NOTES.md`.

## Related patterns (planned)

- **broker-sidecar** — materialize from OpenBao/Vault for an unchanged file-reader
- **fifo-stream** — named pipe, zero-disk, for read-once sequential readers
- **fuse-decrypt** — FUSE filesystem decrypting on read (handles writes too)
- **dynamic-credential-shim** — static password → OpenBao dynamic/static role behind the same file
- **tpm-sealed-bootstrap** — how the materializer authenticates without a stored secret
