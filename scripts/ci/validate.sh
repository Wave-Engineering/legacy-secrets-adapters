#!/usr/bin/env bash
# scripts/ci/validate.sh — smoke-test the catalog.
#
# This repo ships runnable demos, not a unit-test suite, so "validation" means:
# every pattern's Python compiles, its demo runs end-to-end, and (where a pattern
# carries one) its slide deck builds deterministically and stays self-contained.
#
# Run from anywhere: ./scripts/ci/validate.sh
set -euo pipefail
cd "$(dirname "$0")/../.."

echo "== py_compile (all pattern + tool Python) =="
python3 -m py_compile patterns/*/*.py tools/*.py

echo "== cone-of-silence: engine demo (cone.py demo) =="
( cd patterns/cone-of-silence && python3 cone.py demo >/dev/null )

echo "== cone-of-silence: interactive demo (demonstrate.py, scripted) =="
( cd patterns/cone-of-silence \
    && printf '1\n\n3\n\n\n\n\n\n4\n\n\n\n\n2\n\n3\n\n\n\n\n4\n\n\n\n6\n' \
       | python3 demonstrate.py >/dev/null )

echo "== cone-of-silence: deck builds deterministically =="
python3 tools/build_deck.py >/dev/null
h1=$(sha256sum patterns/cone-of-silence/deck.html | cut -d' ' -f1)
python3 tools/build_deck.py >/dev/null
h2=$(sha256sum patterns/cone-of-silence/deck.html | cut -d' ' -f1)
[ "$h1" = "$h2" ] || { echo "FAIL: deck.html is not deterministic ($h1 != $h2)"; exit 1; }

echo "== cone-of-silence: deck is self-contained (no external fetches) =="
if grep -Eq '<script[^>]+src=|rel="stylesheet"' patterns/cone-of-silence/deck.html; then
  echo "FAIL: deck.html references an external resource"; exit 1
fi

echo "✅ validate.sh: all checks passed"
