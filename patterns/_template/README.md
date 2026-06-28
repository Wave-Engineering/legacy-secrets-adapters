# <Pattern Name>

*<one-line essence — the metaphor, and what it does in plain terms>*

<!--
  Copy this directory to patterns/<your-pattern-name>/ (kebab-case) and fill in
  the sections below. Keep the skeleton headings in this order — consistency
  across patterns is what makes the catalog navigable. Delete these comments.
-->

## Context — when you're here

- <the situation + constraints that make this pattern the right fit>
- <e.g. "the app can't be changed", "the secret must be recovered, not just verified">

## Forces

- <the competing pressures the pattern has to resolve>

## Solution

<the mechanism in a few sentences — what you actually do>

## How it works

```
<a small ASCII diagram or flow — what sits where, what moves at runtime>
```

## Run the demo

```bash
./<entrypoint>          # what it does
```

Requirements: <runtime + deps>. <Any optional niceties.>

| File | Role |
|------|------|
| `<file>` | <role> |

## Tradeoffs / residual exposure

<Be honest. What does this NOT protect against? What's the realistic bar?
List the residual exposure and the mitigations that layer on top.>

## Production hardening

<How this looks in a real deployment vs. the demo — key custody, isolation,
rotation, etc.>

## Related patterns

- **<other-pattern>** — <one-line essence and when you'd reach for it instead>
