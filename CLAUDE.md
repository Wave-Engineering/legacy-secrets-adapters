# Project Instructions for Claude Code

`legacy-secrets-adapters` — a **catalog of patterns** for getting plaintext secrets out
of legacy apps that can't be changed. Each pattern is a self-contained write-up plus a
runnable demo. Read this at session start.

## What this repo is

- A pattern catalog, not an application. The deliverable of each pattern is *understanding
  you can run* — a write-up that teaches and a demo that proves the property.
- New work starts from [`docs/decision-guide.md`](docs/decision-guide.md) (which branch is
  uncovered?) and follows [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Platform & workflow

- **Host:** GitHub (`gh` CLI). **Default branch:** `main`. Use "PR".
- **Issue-first.** Never start work without an issue. Branch `feature/<issue#>-<slug>`; PR to `main`.
- **No direct commits to `main`.** Nothing committed without review; nothing pushed without
  the user's go.
- **Commit/PR identity:** GitHub, so the org-specific GitLab identity rule does NOT apply
  here — commit as the global git identity.

## Hard rules (security catalog)

1. **Never commit a real secret or key.** Use obvious fakes; gitignore every runtime artifact
   (decrypted files, keys, sockets) with a pattern-local `.gitignore`.
2. **Never overclaim.** Every pattern's "Tradeoffs" section must state what it does *not*
   protect against. Honesty about residual exposure is the catalog's credibility.
3. **The demo must run.** A pattern whose demo doesn't execute end-to-end is not done.

## Structure

```
patterns/<name>/   one pattern: README (the skeleton) + a runnable demo (+ optional NOTES.md)
patterns/_template/  copy-me skeleton for a new pattern
docs/decision-guide.md   which pattern fits a given situation
CONTRIBUTING.md    how to add a pattern + conventions
```

The pattern README skeleton: **Context · Forces · Solution · How it works · Run the demo ·
Tradeoffs · Production hardening · Related**.
