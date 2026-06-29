#!/usr/bin/env bash
# setup.sh — configure the OpenBao database secrets engine against Postgres, with a STATIC role.
#
# A static role = OpenBao manages ONE fixed Postgres user's password and rotates it on a schedule.
# Fixed username (pool-friendly), no human knows the password. (Dynamic roles — a NEW user per
# short lease — are a small extension, left to the reader.)
#
# Bootstrap secrets (the OpenBao dev token, the PG superuser password) are obvious dev values,
# out of scope — see README "Bootstrap secret — out of scope".
set -euo pipefail

# Pinned to the local demo container. NEVER inherit an ambient BAO_ADDR/BAO_TOKEN — they may
# point at a real server. Hard safety guard (unconditional assignment, not `:-`).
export BAO_ADDR="http://127.0.0.1:58200"
export BAO_TOKEN="dev-only-root-token"   # BOOTSTRAP SECRET (obvious dev value)
if [[ "$BAO_ADDR" != http://127.0.0.1:* && "$BAO_ADDR" != http://localhost:* ]]; then
  echo "refusing to run against non-local BAO_ADDR=$BAO_ADDR" >&2; exit 1
fi
PG="postgresql://postgres:bootstrap-only-pg-superpw@127.0.0.1:55432/appdb?sslmode=disable&gssencmode=disable"

echo "→ waiting for OpenBao + Postgres ..."
for _ in $(seq 1 30); do bao status >/dev/null 2>&1 && break; sleep 1; done
for _ in $(seq 1 30); do psql "$PG" -tAc 'select 1' >/dev/null 2>&1 && break; sleep 1; done

echo "→ creating the fixed app role OpenBao will manage (app_pg_user)"
psql "$PG" -v ON_ERROR_STOP=1 -q -c \
  "DROP ROLE IF EXISTS app_pg_user; CREATE ROLE app_pg_user LOGIN PASSWORD 'rotated-away-immediately';"

echo "→ enabling + configuring the database secrets engine"
bao secrets enable database >/dev/null 2>&1 || true
bao write database/config/appdb \
  plugin_name=postgresql-database-plugin \
  allowed_roles="app-static" \
  connection_url="postgresql://{{username}}:{{password}}@postgres:5432/appdb?sslmode=disable" \
  username="postgres" password="bootstrap-only-pg-superpw" >/dev/null

echo "→ rotating OpenBao's own admin password (now no human knows it)"
bao write -f database/rotate-root/appdb >/dev/null

echo "→ defining the STATIC role (OpenBao owns + rotates app_pg_user's password)"
bao write database/static-roles/app-static \
  db_name=appdb username="app_pg_user" rotation_period=24h >/dev/null

echo "✅ setup complete — 'bao read database/static-creds/app-static' now yields a managed credential."
