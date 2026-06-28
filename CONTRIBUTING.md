# Contributing a pattern

This is a **catalog**: one pattern per directory, each a self-contained write-up
**plus a runnable demo**. A pattern that can't be run and felt isn't done.

## Add a pattern

1. Pick a decision branch that isn't covered yet — see [`docs/decision-guide.md`](docs/decision-guide.md).
2. Open an issue, then branch: `feature/<issue#>-<pattern-slug>`.
3. `cp -r patterns/_template patterns/<pattern-slug>` (kebab-case name).
4. Fill in `README.md` following the skeleton — keep the heading order.
5. Add a **runnable demo** (a script, a `Makefile`, whatever — but it must actually run).
6. Optionally add a `NOTES.md` for the production deep-dive.
7. Add a row to the catalog table in the top-level [`README.md`](README.md).
8. Open a PR to `main`. The demo must run; no merge without review.

## Conventions

- **Directory names** are kebab-case (`cone-of-silence`, `broker-sidecar`).
- **Never commit a real secret or key.** Use an obviously-fake demo value (e.g.
  `S3cr3t-Pg-Pass`). Gitignore every runtime artifact the demo generates (decrypted
  files, keys, sockets) with a pattern-local `.gitignore`.
- **Be honest about residual exposure.** Every pattern's "Tradeoffs" section must
  state what it does *not* protect against. Overclaiming is the one unforgivable sin
  in a security catalog — see the Cone of Silence's "Transparency in Secrecy" appendix
  for the bar.
- **Demos should be low-dependency.** Prefer the standard library + one well-known
  package over a framework. Degrade gracefully when an optional tool is missing.
- **Teach, don't just ship.** The demo should let a skeptic *see* the property hold
  (e.g. `grep` the disk and find nothing), not just assert it.

## The skeleton

Each pattern `README.md` follows: **Context · Forces · Solution · How it works ·
Run the demo · Tradeoffs · Production hardening · Related**. The copy-me version is
[`patterns/_template/README.md`](patterns/_template/README.md).
