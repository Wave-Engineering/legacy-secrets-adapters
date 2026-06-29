# Dynamic Credential Shim — production deep-dive

## The real OpenBao wiring (what `setup.sh` does)

```bash
# 1. the database secrets engine, pointed at Postgres with an admin connection
bao secrets enable database
bao write database/config/appdb \
    plugin_name=postgresql-database-plugin \
    allowed_roles="app-static" \
    connection_url="postgresql://{{username}}:{{password}}@postgres:5432/appdb?sslmode=disable" \
    username="postgres" password="<admin>"

# 2. rotate OpenBao's own admin password — now NO human knows it
bao write -f database/rotate-root/appdb

# 3. the STATIC role: OpenBao owns + rotates a FIXED, pre-existing user's password
bao write database/static-roles/app-static \
    db_name=appdb username="app_pg_user" rotation_period=24h

# read the current managed credential (stable username, rotating password)
bao read database/static-creds/app-static
# force a rotation (the demo does this; production uses the schedule)
bao write -f database/rotate-role/app-static
```

The fixed user must **pre-exist** (`CREATE ROLE app_pg_user LOGIN …`); OpenBao rotates its password
on first write and every `rotation_period` thereafter.

## Static vs dynamic roles

| | **Static role** (this pattern) | **Dynamic role** (the reader's exercise) |
|---|---|---|
| Identity | one **fixed** username | a **new** username per lease |
| What rotates | the password, on a schedule | the whole credential expires (`VALID UNTIL`), then `DROP`ed |
| Leak window | until next `rotation_period` | until lease TTL (can be minutes) |
| Connection pools | **friendly** — username never changes | **hostile** — new logins need the new user; pool refills break |
| Config | `static-roles` (no SQL) | `roles` with `creation_statements` / `revocation_statements` |

For a legacy app you can't change — especially one with a connection pool — **static roles are the
pragmatic default**: the strongest leak-window improvement you can make *without* breaking the
pool. Dynamic roles are a strict upgrade on leak-window and a strict downgrade on pool-friendliness;
swapping `static-roles`/`static-creds`/`rotate-role` for `roles`/`creds` with creation statements is
the whole change — left to the reader.

## The re-read tension (why this composes with a reconnect)

Rotation only helps if the consumer eventually uses the new credential. On rotation:

- **existing** Postgres connections keep working (Postgres doesn't re-auth a live session);
- the **next new** connection needs the new password.

So the shim must rewrite the file *and* the reader must re-read it on its next connect. A reader
that opens one pool at boot and holds it forever won't feel a rotation until it reconnects or
restarts. Practical rule: set `rotation_period` to comfortably exceed the reader's reconnect/restart
cadence, so a rotation never lands mid-session — or pair with a reader that reconnects on error.

## Single-OpenBao availability — a SPOF for *rotation*, not for *use*

A static role's password has **no consumer-side expiry** — it's just a password Postgres accepts.
So if OpenBao is down:

- already-issued credentials **keep working** — the app stays up;
- only **rotation pauses** — a mild, temporary *security* degradation (the password lives longer
  than intended), not an availability outage.

This is the opposite of a **dynamic** role with a short `VALID UNTIL`, where Postgres itself enforces
the deadline: when it passes and OpenBao (the only issuer) is down, new logins fail — a hard outage.
That asymmetry is another reason static roles fit a load-bearing, can't-change-it reader. The real
fix for the SPOF is OpenBao HA (integrated Raft), not lengthening TTLs.

## Composition with the Cone of Silence

This pattern owns the **credential lifecycle** (rotation, leak-expiry); it does not own **delivery**.
The shim here writes a plain file for clarity. In production, point the shim at a Cone tmpfs path
(`../cone-of-silence`) so the rotating credential is also never at rest on disk — the two patterns
compose cleanly: the Cone keeps it in RAM, the shim keeps it short-lived.

## Bootstrap secret

The OpenBao token the shim uses (and the PG superuser password) are this demo's bootstrap secrets —
obvious dev values, hardcoded on purpose, **out of scope**. Anchoring them without a stored secret
(AppRole + response-wrapping, a TPM-sealed token, cloud instance identity) is the orthogonal
bootstrap-secret pattern family — see `../../docs/decision-guide.md`.
