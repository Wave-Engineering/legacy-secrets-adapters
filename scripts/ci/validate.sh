#!/usr/bin/env bash
# scripts/ci/validate.sh — smoke-test the catalog.
#
# This repo ships runnable demos, not a unit-test suite, so "validation" means:
# every pattern's Python compiles, its demo runs end-to-end, and (where a pattern
# carries one) its slide deck builds deterministically and stays self-contained.
# Demos that need Docker run only when Docker is present (skipped-with-notice otherwise).
#
# Run from anywhere: ./scripts/ci/validate.sh
set -euo pipefail
shopt -s nullglob
cd "$(dirname "$0")/../.."

echo "== py_compile (all pattern + tool Python) =="
python3 -m py_compile delivery-pattern-demos/*/*.py bootstrap-pattern-demos/*/*.py tools/*.py

echo "== cone-of-silence: engine demo (cone.py demo) =="
( cd delivery-pattern-demos/cone-of-silence && python3 cone.py demo >/dev/null )

echo "== cone-of-silence: interactive demo (demonstrate.py, scripted) =="
( cd delivery-pattern-demos/cone-of-silence \
    && printf '1\n\n3\n\n\n\n\n\n4\n\n\n\n\n2\n\n3\n\n\n\n\n4\n\n\n\n6\n' \
       | python3 demonstrate.py >/dev/null )

echo "== decks build deterministically + self-contained =="
for wt in delivery-pattern-demos/*/walkthrough.py bootstrap-pattern-demos/*/walkthrough.py; do
  pat=$(dirname "$wt")
  python3 tools/build_deck.py "$pat" >/dev/null
  h1=$(sha256sum "$pat/deck.html" | cut -d' ' -f1)
  python3 tools/build_deck.py "$pat" >/dev/null
  h2=$(sha256sum "$pat/deck.html" | cut -d' ' -f1)
  [ "$h1" = "$h2" ] || { echo "FAIL: $pat/deck.html not deterministic"; exit 1; }
  grep -Eq '<script[^>]+src=|rel="stylesheet"' "$pat/deck.html" \
    && { echo "FAIL: $pat/deck.html references an external resource"; exit 1; } || true
  echo "   ✓ $(basename "$pat") deck"
done

echo "== every pattern ships both enlighten.html (why/what) and deck.html (how) =="
for pat in delivery-pattern-demos/*/ bootstrap-pattern-demos/*/; do
  [ "$(basename "$pat")" = "_template" ] && continue
  for f in enlighten.html deck.html; do
    [ -f "$pat$f" ] || { echo "FAIL: $pat is missing $f (every pattern needs both)"; exit 1; }
  done
  echo "   ✓ $(basename "$pat")"
done

echo "== fuse-decrypt: end-to-end demo =="
if test -c /dev/fuse; then
  ( cd delivery-pattern-demos/fuse-decrypt && python3 demo.py )
else
  echo "   ⚪ /dev/fuse not available — skipping the live demo (py_compile + decks still validated)"
fi

echo "== dynamic-credential-shim: live OpenBao + Postgres demo =="
if docker info >/dev/null 2>&1; then
  ( cd delivery-pattern-demos/dynamic-credential-shim
    trap 'docker compose down -v >/dev/null 2>&1 || true' EXIT
    docker compose down -v >/dev/null 2>&1 || true   # fresh stack (rotate-root makes setup non-idempotent)
    docker compose up -d >/dev/null
    env -u BAO_ADDR -u BAO_TOKEN ./setup.sh >/dev/null
    ./shim.py >/dev/null
    ./legacy_reader.py 2>&1 | grep -q "connected OK" \
      || { echo "FAIL: reader did not connect with the managed credential"; exit 1; }
    # exfiltrate the current password, rotate, and assert the old copy now fails (leak self-expires)
    export BAO_ADDR=http://127.0.0.1:58200 BAO_TOKEN=dev-only-root-token   # LOCAL container only
    OLD=$(bao read -format=json database/static-creds/app-static \
          | python3 -c 'import json,sys;print(json.load(sys.stdin)["data"]["password"])')
    bao write -f database/rotate-role/app-static >/dev/null
    if psql "postgresql://app_pg_user:${OLD}@127.0.0.1:55432/appdb?sslmode=disable&gssencmode=disable" \
         -tAc 'select 1' >/dev/null 2>&1; then
      echo "FAIL: the exfiltrated credential still works after rotation"; exit 1
    fi
    echo "   ✓ reader connected; rotated; the exfiltrated credential was rejected" )
else
  echo "   ⚪ Docker not available — skipping the live demo (py_compile + decks still validated)"
fi

echo "✅ validate.sh: all checks passed"
