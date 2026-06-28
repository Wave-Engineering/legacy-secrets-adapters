# legacy-secrets-adapters

*A catalog of patterns for getting plaintext secrets out of legacy apps you can't change.*

Some applications read their credentials from a plaintext file (or a fixed path, or an env var) and will never
be re-released to do otherwise. This repo collects **adapter patterns** that protect those secrets *around* the
unchangeable app — each pattern is a self-contained write-up plus a runnable demo.

## When to reach for these

A quick decision tree (full version coming in `docs/decision-guide.md`):

1. **Does the app need the plaintext, or only to *verify* a value?** If it only verifies → hash it (Argon2id),
   don't encrypt. These patterns are for when the plaintext must be *recovered and used*.
2. **Can the secret be minted on demand** (a DB password, an SSH cert) **or only held** (a third-party API key)?
   Mintable → prefer short-lived/dynamic issuance. Opaque → protect the held value.
3. **Can you change the reader?** If not, the fix must be *transparent* — change what's behind the path, not the app.

## Catalog

| Pattern | Essence | Status |
|---|---|---|
| [cone-of-silence](patterns/cone-of-silence/) | encrypted at rest, decrypted only into a RAM (tmpfs) file at the path the app already reads | ✅ available |
| broker-sidecar | materialize a secret from OpenBao/Vault into a file for an unchanged reader | 🅿️ planned |
| fifo-stream | named pipe (zero disk) for read-once sequential readers | 🅿️ planned |
| fuse-decrypt | FUSE filesystem that decrypts on read (and handles writes) | 🅿️ planned |
| dynamic-credential-shim | replace a static DB password with an OpenBao dynamic/static role behind the same file | 🅿️ planned |
| tpm-sealed-bootstrap | how a materializer authenticates to its key source without a stored secret | 🅿️ planned |

## How patterns are structured

Each `patterns/<name>/` carries a `README.md` that follows one skeleton —
**Context · Forces · Solution · How it works · Run the demo · Tradeoffs · Production hardening · Related** —
plus a runnable demo and, where useful, a `NOTES.md` deep-dive.

## License

See [LICENSE](LICENSE).
