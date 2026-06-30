# legacy-secrets-adapters

[![Validate catalog](https://github.com/Wave-Engineering/legacy-secrets-adapters/actions/workflows/validate.yml/badge.svg)](https://github.com/Wave-Engineering/legacy-secrets-adapters/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Patterns: 8](https://img.shields.io/badge/patterns-8-blueviolet.svg)](#catalog)

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

## Quick start

```bash
git clone https://github.com/Wave-Engineering/legacy-secrets-adapters.git
cd legacy-secrets-adapters

# Pick a pattern and run its demo (example: fifo-stream)
cd delivery-pattern-demos/fifo-stream
python3 demonstrate.py

# Or browse a pattern's concept page
open delivery-pattern-demos/fifo-stream/enlighten.html
```

Each demo is self-contained — follow the on-screen menu. Infrastructure-using demos
(dynamic-credential-shim, broker-sidecar) spin up Docker containers and tear them down
on exit.

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

**[fifo-stream](delivery-pattern-demos/fifo-stream/)** — Named pipe; the secret streams
through kernel memory and never exists on any filesystem. Reach for this when the app reads
its config once, sequentially, and you want the strongest possible guarantee: zero disk
footprint, zero RAM file, zero window. Doesn't work if the app seeks, re-reads, or mmaps
the file.

**[cone-of-silence](delivery-pattern-demos/cone-of-silence/)** — Encrypted at rest,
decrypted into a RAM-backed (tmpfs) file at the path the app already reads. The simplest
"grep-clean disk" pattern — low moving parts, no daemon, works for any single-file secret.
Doesn't protect against a co-located attacker who can read the tmpfs mount; pair with
namespace isolation or fifo-stream if that's your threat.

**[dynamic-credential-shim](delivery-pattern-demos/dynamic-credential-shim/)** — OpenBao
mints a short-lived DB credential and writes it where the app reads; a leaked copy
self-expires. Reach for this when the secret is *mintable* (a database password you control
issuance of) and you want temporal protection: a stolen credential is dead after its TTL.
Doesn't help with opaque third-party keys you can't rotate.

**[broker-sidecar](delivery-pattern-demos/broker-sidecar/)** — A long-running sidecar
fetches any secret from the vault, renders it through a Jinja2 template into the app's
native config format, and watches for rotation. The general-purpose pattern when you need
arbitrary secret types, arbitrary output formats, and automatic refresh. More operational
surface than simpler patterns — a daemon to monitor, a vault dependency to maintain.

**[fuse-decrypt](delivery-pattern-demos/fuse-decrypt/)** — A FUSE filesystem that stores
ciphertext on disk and decrypts on every read syscall, transparently. The pattern of last
resort: when the app does arbitrary POSIX I/O (seek, write-back, mmap) and nothing simpler
can satisfy its file contract. Requires `/dev/fuse` and kernel module support; any
co-located process that mounts the FUSE path reads plaintext.

### Bootstrap-secret (orthogonal)

**[cloud-instance-identity](bootstrap-pattern-demos/cloud-instance-identity/)** — The
machine's cloud-assigned IAM role IS the bootstrap credential. No stored secret, no
delivery channel, no TTL to manage — the hypervisor's metadata endpoint handles it. Reach
for this on EC2/GCE/Azure; impossible off-cloud.

**[approle-response-wrapping](bootstrap-pattern-demos/approle-response-wrapping/)** — A
trusted deployer (Ansible, CI/CD) delivers a single-use response-wrapped token at deploy
time. Consumed on unwrap, dead after its TTL, replay-proof even if intercepted. Reach for
this when you have a deployment pipeline but no TPM or cloud identity; useless without a
delivery channel.

**[tpm-sealed-bootstrap](bootstrap-pattern-demos/tpm-sealed-bootstrap/)** — Seal the
bootstrap credential to the machine's TPM2 PCR state. Only this hardware can unseal it;
a stolen disk image is inert elsewhere. The strongest hardware-bound bootstrap — reach for
this on bare metal or VMs with vTPM. Requires TPM2 hardware and systemd >= 250; no
cross-machine portability.

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

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for how to add a pattern, conventions, and the
pattern README skeleton.

## Changelog

See [`CHANGELOG.md`](CHANGELOG.md) for release history.

## License

See [LICENSE](LICENSE).
