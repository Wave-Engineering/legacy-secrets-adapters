# Contributing a pattern

This is a **catalog**: one pattern per directory, each a self-contained write-up
**plus a runnable demo**. A pattern that can't be run and felt isn't done.

## Add a pattern

1. Pick a decision branch that isn't covered yet — see [`docs/decision-guide.md`](docs/decision-guide.md).
2. Open an issue, then branch: `feature/<issue#>-<pattern-slug>`.
3. `cp -r patterns/_template patterns/<pattern-slug>` (kebab-case name).
4. Fill in `README.md` following the skeleton — keep the heading order.
5. Add a **runnable demo** (a script, a `Makefile`, whatever — but it must actually run).
6. Write **both** teaching artifacts (see below): `enlighten.html` (the why & what) and
   `deck.html` (the how, built from `walkthrough.py`). A pattern needs both.
7. Optionally add a `NOTES.md` for the production deep-dive.
8. Add a row to the catalog table in the top-level [`README.md`](README.md).
9. Open a PR to `main`. The demo must run; no merge without review.

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

## Bootstrap secret — out of scope (a hard convention)

Every delivery pattern has a **bootstrap secret**: the credential its materializer/broker uses to
reach its *own* key source (a Vault token, a KMS key, a TPM handle). How to anchor that without a
stored secret — the turtles-to-silicon problem — is **orthogonal** to what a delivery pattern teaches,
and it's a whole separate pattern family ([`docs/decision-guide.md`](docs/decision-guide.md)).

So in **every** demo:

- **Hardcode the bootstrap secret obviously** (an unmistakable dev value) and label it — never
  half-solve key custody inline.
- Add a **`## Bootstrap secret — out of scope`** section to the pattern's `README.md` (see the
  template) naming the bootstrap secret and pointing at the bootstrap-secret family.

This keeps each demo's lesson clean and avoids implying a pattern "solves" key custody when it doesn't.

## The skeleton

Each pattern `README.md` follows: **Context · Forces · Solution · How it works ·
Run the demo · Tradeoffs · Production hardening · Related**. The copy-me version is
[`patterns/_template/README.md`](patterns/_template/README.md).

## Two artifacts, both required: the why/what and the how

Every pattern ships **both** of these — they're a pair, and `scripts/ci/validate.sh` checks that
both exist:

- **`enlighten.html` — the *why* and the *what*.** A hand-written page: the problem, the concept,
  diagrams, the honest tradeoffs, and pointers to related patterns. It builds the reader's mental
  model. Match the existing patterns' dark-theme aesthetic and keep it self-contained (no external
  fetches). Start from the Cone of Silence's `enlighten.html`.
- **`deck.html` — the *how*.** The terminal walk-through, generated from a `walkthrough.py` manifest:

  ```bash
  python3 tools/build_deck.py patterns/<pattern>
  ```

  One self-contained file, sendable as-is. A pure function of the manifest (fixed prompt, frozen
  output, no timestamps) → byte-identical on every run. Regenerate it whenever you edit
  `walkthrough.py`, and commit the result.

Show the *how* without the *why* and it's a magic trick; the *why* without the *how* and it's a
lecture. Cross-link them — the deck's closing points at `enlighten.html`, and `enlighten.html`
points at the deck.
