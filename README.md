# legacy-secrets-adapters

*A catalog of patterns for getting plaintext secrets out of legacy apps you can't change.*

Some applications read their credentials from a plaintext file (or a fixed path, or an env var) and will never
be re-released to do otherwise. This repo collects **adapter patterns** that protect those secrets *around* the
unchangeable app — each pattern is a self-contained write-up plus a runnable demo.

## Use this with an AI partner

This catalog is designed to be loaded into your AI model of choice as domain expertise.
Point it at this repo, describe your situation, and have a conversation:

> *"I've got a legacy Postgres app on EC2. Reads creds from /etc/app/db.conf. Can't
> change the app. Compliance wants rotation and a grep-clean disk. What do I do?"*

The model holds 8 patterns, their compositions, their honest limitations, and the
decision logic in working memory. You hold the constraints, the deadlines, and the
judgment. Between you, you'll converge on a design — and then build it together.

The skill definition lives at [`skills/secrets-advisor/SKILL.md`](skills/secrets-advisor/SKILL.md).
Feed it to your model as a system prompt, give it access to this repo and your codebase,
and go.

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

| Pattern | Essence |
|---|---|
| [fifo-stream](delivery-pattern-demos/fifo-stream/) | Named pipe — secret streams through kernel memory, never exists on any filesystem |
| [cone-of-silence](delivery-pattern-demos/cone-of-silence/) | Encrypted at rest, decrypted only into a RAM (tmpfs) file at the path the app reads |
| [dynamic-credential-shim](delivery-pattern-demos/dynamic-credential-shim/) | OpenBao-managed rotating DB credential — a leak self-expires |
| [broker-sidecar](delivery-pattern-demos/broker-sidecar/) | Sidecar fetches from vault, templates into any config format, watches for rotation |
| [fuse-decrypt](delivery-pattern-demos/fuse-decrypt/) | FUSE filesystem: ciphertext on disk, decrypt-on-read per syscall for arbitrary POSIX I/O |

### Bootstrap-secret (orthogonal)

| Pattern | Essence |
|---|---|
| [cloud-instance-identity](bootstrap-pattern-demos/cloud-instance-identity/) | The machine's IAM role IS the bootstrap credential — no stored secret |
| [approle-response-wrapping](bootstrap-pattern-demos/approle-response-wrapping/) | Single-use wrapped token delivered by CD/Ansible — consumed on unwrap, dead after TTL |
| [tpm-sealed-bootstrap](bootstrap-pattern-demos/tpm-sealed-bootstrap/) | Seal the bootstrap credential to the machine's TPM2 — only this machine can unseal |

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
