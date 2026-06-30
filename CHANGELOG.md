# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] - 2026-06-30

### Added

- **5 delivery patterns** — fifo-stream, cone-of-silence, dynamic-credential-shim,
  broker-sidecar, fuse-decrypt — each with README, interactive TUI demo, enlighten page,
  and generated slide deck.
- **3 bootstrap patterns** — cloud-instance-identity, approle-response-wrapping,
  tpm-sealed-bootstrap — same teaching artifacts per pattern.
- **Decision guide** (`docs/decision-guide.md`) — three-question narrowing tree for
  pattern selection.
- **Secrets Advisor skill** (`skills/secrets-advisor/SKILL.md`) — Socratic AI/human
  partnership for pattern selection and implementation.
- **Infographic metrics** — at-a-glance complexity/security/ops-burden bars on every
  enlighten page.
- **CI pipeline** — `scripts/ci/validate.sh` smoke-tests all demos; GitHub Actions
  workflow runs on push to main and on PRs.
- **Deck generator** (`tools/build_deck.py`) — deterministic HTML slide deck from each
  pattern's `walkthrough.py` manifest.
- **Defence in Depth compositions** — documented temporal + spatial pairings
  (shim+cone, broker+cone, shim+fifo).
- **try/finally teardown** — all infrastructure-using demos guarantee cleanup on crash.
