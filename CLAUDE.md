# Project Instructions for Claude Code

`legacy-secrets-adapters` — a **catalog of patterns** for getting plaintext secrets out of
legacy apps that can't be changed. Each pattern is a self-contained write-up plus a runnable
demo. Read this at session start.

> Tailored for THIS repo. It deliberately omits the wave-pattern / kahuna / WAVE_AXIOMS /
> merge-queue / Discord-fleet machinery from the org template — none of it has a referent here,
> and a pointer that goes nowhere is worse than no pointer.

## What this repo is

- A pattern catalog, not an application. Each pattern's deliverable is *understanding you can
  run*: a write-up that teaches, and a demo that lets a skeptic **see** the property hold
  (e.g. `grep` the disk and find nothing).
- Start new work from `docs/decision-guide.md` (which decision-tree leaf is uncovered?) and
  follow `CONTRIBUTING.md`.

## Platform & workflow

- **Host:** GitHub (`gh` CLI). **Default branch:** `main`. Say "PR".
- **Issue-first.** Never start work without an issue. Branch `type/<issue#>-slug`
  (`feature` / `fix` / `doc` / `chore` / `bug` — prefixes are singular); PR targets `main`. No direct commits to `main`.
- **On merge, close all linked issues** (`Closes #N`) and verify closure.
- **Commit identity:** this is GitHub, so the GitLab verified-email rule does NOT apply — commit
  as the global git identity.

## MANDATORY: gates

1. **Local testing before push.** Run `./scripts/ci/validate.sh` before pushing — it
   `py_compile`s every pattern/tool, runs each demo end-to-end, and checks deck determinism.
   A session-scoped pre-push hook blocks `git push` until a recognized test command (this
   script) has passed this session.
2. **Pre-commit gate.** When work is done, run `/precheck`, present the checklist, then **STOP**
   and wait for `/scp` / `/scpmr` / `/scpmmr` / an affirmative. No autonomous commits. Asking
   "shall I run /precheck?" is itself the bug — just run it; the checklist is the approval surface.

## Hard rules (it's a security catalog)

1. **Never commit a real secret or key.** Use an obvious fake (e.g. `S3cr3t-Pg-Pass`); gitignore
   every runtime artifact a demo generates (decrypted files, keys, sockets) via a pattern-local
   `.gitignore`.
2. **Never overclaim.** Every pattern's "Tradeoffs" section must state what it does *not* protect
   against. Honesty about residual exposure is the catalog's credibility — see the Cone of
   Silence's "Transparency in Secrecy" appendix for the bar.
3. **The demo must run.** A pattern whose demo doesn't execute end-to-end is not done.

## Structure

```
patterns/<name>/             one pattern: README (the skeleton) + a runnable demo (+ optional NOTES.md)
patterns/<name>/walkthrough.py   (optional) the demo walkthrough as DATA — drives the TUI AND the deck
patterns/_template/          copy-me skeleton for a new pattern
tools/build_deck.py          render a pattern's walkthrough.py -> a self-contained, deterministic deck.html
scripts/ci/validate.sh       smoke-test the catalog (the local-testing entry point)
docs/decision-guide.md       which pattern fits a given situation
CONTRIBUTING.md              how to add a pattern + conventions
```

Pattern README skeleton: **Context · Forces · Solution · How it works · Run the demo ·
Tradeoffs · Production hardening · Related**.

## Code standards

- Python is the demo language. Keep demos low-dependency (stdlib + one well-known package; degrade
  gracefully when an optional tool like `bat` is absent). Don't introduce new formatters/linters.
- Discover tooling rather than assuming — `scripts/ci/validate.sh` is the entry point.
- **Slide decks are generated, never hand-edited.** Edit `walkthrough.py`, then rebuild with
  `python3 tools/build_deck.py patterns/<name>` and commit the regenerated `deck.html`. The deck
  is a pure function of the manifest (fixed prompt, frozen output) — byte-identical every run.

## Commit / PR format

- Commits: `type(scope): brief description`, optional body, `Closes #N`. Types: `feat` `fix` `docs`
  `refactor` `test` `chore`.
- PRs: `## Summary` · `## Changes` · `## Linked Issues` (`Closes #N`) · `## Test Plan` (what was
  actually run, not what could be).

## Default to action

If a next step is safe, understood, and in your lane, do it and report — don't stop to ask.
Legitimate stops: a genuinely new irreversible / outward-facing action not yet agreed to, or a real
design fork where the user's choice changes what you build. **Agreement persists** — don't
re-confirm each step of directed work. The `/precheck` checklist *is* the commit-approval surface;
don't narrate a second gate.

## Agent identity

Per-session Dev-Name/Dev-Avatar via `/name` (ephemeral). Dev-Team is persisted below.

Dev-Team: oaw
