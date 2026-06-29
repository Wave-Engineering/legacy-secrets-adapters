# legacy-secrets-adapters

*A catalog of patterns for getting plaintext secrets out of legacy apps you can't change.*

Some applications read their credentials from a plaintext file (or a fixed path, or an env var) and will never
be re-released to do otherwise. This repo collects **adapter patterns** that protect those secrets *around* the
unchangeable app — each pattern is a self-contained write-up plus a runnable demo.

## When to reach for these

A quick decision tree (full version: [`docs/decision-guide.md`](docs/decision-guide.md)):

1. **Does the app need the plaintext, or only to *verify* a value?** If it only verifies → hash it (Argon2id),
   don't encrypt. These patterns are for when the plaintext must be *recovered and used*.
2. **Can the secret be minted on demand** (a DB password, an SSH cert) **or only held** (a third-party API key)?
   Mintable → prefer short-lived/dynamic issuance. Opaque → protect the held value.
3. **Can you change the reader?** If not, the fix must be *transparent* — change what's behind the path, not the app.

## Catalog

Two **orthogonal** axes. *Delivery & lifecycle* patterns get a secret to an unchangeable app and govern
its lifetime. *Bootstrap-secret* patterns answer the question every delivery pattern leaves open — "how
does the deliverer authenticate to its *own* key source without a stored secret?" — and are deliberately
**out of scope** inside each delivery demo (see [`CONTRIBUTING.md`](CONTRIBUTING.md)).

### Delivery & lifecycle

| Pattern | Essence | Status |
|---|---|---|
| [cone-of-silence](delivery-pattern-demos/cone-of-silence/) | encrypted at rest, decrypted only into a RAM (tmpfs) file at the path the app already reads | ✅ available |
| [dynamic-credential-shim](delivery-pattern-demos/dynamic-credential-shim/) | static DB password → an OpenBao-managed static role (rotated password, stable username) behind the same file, so a leak self-expires | ✅ available |
| broker-sidecar | materialize a secret from OpenBao/Vault into a file for an unchanged reader | 🅿️ planned |
| fifo-stream | named pipe (zero disk) for read-once sequential readers | 🅿️ planned |
| fuse-decrypt | FUSE filesystem that decrypts on read (and handles writes) | 🅿️ planned |

### Bootstrap-secret (orthogonal)

| Pattern | Essence | Status |
|---|---|---|
| tpm-sealed-bootstrap | how a materializer authenticates to its key source without a stored secret (turtles → silicon) | 🅿️ planned |

## Roadmap & design intentions

See [`docs/sketchbook.md`](docs/sketchbook.md) for per-pattern design briefs — mechanism, demo
plan, honest tradeoffs — used as the spec source for the wave campaign.

## How patterns are structured

Each pattern lives in one of two parallel trees — `delivery-pattern-demos/<name>/` or
`bootstrap-pattern-demos/<name>/` — and carries a `README.md` that follows one skeleton
(**Context · Forces · Solution · How it works · Run the demo · Tradeoffs · Production hardening ·
Related**), a runnable demo, and **two teaching artifacts that require each other:
`enlighten.html` (the *why & what* — concept + diagrams + related) and `deck.html` (the *how* —
the terminal walk-through)**. A `NOTES.md` deep-dive where useful.

## License

See [LICENSE](LICENSE).
