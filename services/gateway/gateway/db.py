"""Postgres: upstream registry, API keys, audit log. See D-008.

Schema is created on start, idempotently. There is no migration tool in
phase 1; `CREATE TABLE IF NOT EXISTS` is honest about what this is.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from psycopg_pool import AsyncConnectionPool

SCHEMA = """
CREATE TABLE IF NOT EXISTS upstreams (
    id               SERIAL PRIMARY KEY,
    slug             TEXT NOT NULL UNIQUE,
    url              TEXT NOT NULL,
    -- Header name and scheme are stored separately so the registry can
    -- describe "Authorization: Bearer x" and "X-Api-Key: x" with one shape.
    auth_header      TEXT,
    auth_scheme      TEXT,
    -- Encrypted at rest. Never selected into a response or a log line.
    credential_enc   TEXT,
    enabled          BOOLEAN NOT NULL DEFAULT TRUE,
    status           TEXT NOT NULL DEFAULT 'Unknown',
    last_checked     TIMESTAMPTZ,
    last_error       TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    id             SERIAL PRIMARY KEY,
    email          TEXT NOT NULL UNIQUE,
    name           TEXT NOT NULL,
    role           TEXT NOT NULL DEFAULT 'member',
    -- argon2id. NULL until the invite is accepted and a password is set.
    password_hash  TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    disabled_at    TIMESTAMPTZ
);

-- The token itself is a bearer credential until consumed, so only its
-- SHA-256 is stored: database read access must not let someone accept an
-- invite as that person.
CREATE TABLE IF NOT EXISTS invites (
    id          SERIAL PRIMARY KEY,
    email       TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'member',
    token_hash  TEXT NOT NULL UNIQUE,
    created_by  INTEGER REFERENCES users(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ
);

-- Server-side sessions. The cookie carries this opaque id and nothing else:
-- no user id, no role, no signature, nothing a tampered cookie could assert.
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions (user_id);

CREATE TABLE IF NOT EXISTS api_keys (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    prefix      TEXT NOT NULL UNIQUE,
    key_hash    TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'admin',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at  TIMESTAMPTZ
);
-- Added after api_keys shipped without it, so it is a guarded ALTER rather
-- than a column in the CREATE: an existing deployment already has the table.
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id);
-- The chat agent mints one of these per turn and deletes it again when the
-- turn ends. expires_at is the backstop for the case where the process dies
-- mid-turn: an orphaned key stops authenticating on its own.
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;

-- Every tool call, success or failure, from day one.
CREATE TABLE IF NOT EXISTS audit (
    id           BIGSERIAL PRIMARY KEY,
    ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_name    TEXT NOT NULL,
    server_slug  TEXT,
    tool         TEXT,
    duration_ms  INTEGER NOT NULL,
    outcome      TEXT NOT NULL,
    detail       TEXT
);
CREATE INDEX IF NOT EXISTS audit_ts_idx ON audit (ts DESC);
-- Chat turns carry their token cost. NULL for a plain tool call, which has
-- no model behind it. Columns rather than JSON in `detail` so the daily cost
-- is one SUM and the dashboard does not have to parse anything.
ALTER TABLE audit ADD COLUMN IF NOT EXISTS tokens_in  INTEGER;
ALTER TABLE audit ADD COLUMN IF NOT EXISTS tokens_out INTEGER;
"""


@dataclass
class Upstream:
    id: int
    slug: str
    url: str
    auth_header: str | None
    auth_scheme: str | None
    credential_enc: str | None
    enabled: bool
    status: str
    last_error: str | None


class Db:
    def __init__(self, dsn: str) -> None:
        self._pool = AsyncConnectionPool(dsn, min_size=1, max_size=5, open=False)

    async def open(self) -> None:
        await self._pool.open()
        async with self._pool.connection() as c:
            await c.execute(SCHEMA)

    async def close(self) -> None:
        await self._pool.close()

    # ---------------- upstreams ----------------

    async def list_upstreams(self, enabled_only: bool = False) -> list[Upstream]:
        q = ("SELECT id, slug, url, auth_header, auth_scheme, credential_enc, "
             "enabled, status, last_error FROM upstreams")
        if enabled_only:
            q += " WHERE enabled"
        q += " ORDER BY slug"
        async with self._pool.connection() as c:
            rows = await (await c.execute(q)).fetchall()
        return [Upstream(*r) for r in rows]

    async def upsert_upstream(self, slug: str, url: str, auth_header: str | None,
                              auth_scheme: str | None, credential_enc: str | None,
                              enabled: bool = True) -> None:
        async with self._pool.connection() as c:
            await c.execute(
                """INSERT INTO upstreams (slug, url, auth_header, auth_scheme, credential_enc, enabled)
                   VALUES (%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (slug) DO UPDATE SET
                     url=EXCLUDED.url, auth_header=EXCLUDED.auth_header,
                     auth_scheme=EXCLUDED.auth_scheme,
                     credential_enc=COALESCE(EXCLUDED.credential_enc, upstreams.credential_enc),
                     enabled=EXCLUDED.enabled""",
                (slug, url, auth_header, auth_scheme, credential_enc, enabled))

    async def set_enabled(self, slug: str, enabled: bool) -> None:
        async with self._pool.connection() as c:
            await c.execute("UPDATE upstreams SET enabled=%s WHERE slug=%s", (enabled, slug))

    async def set_status(self, slug: str, status: str, error: str | None) -> None:
        async with self._pool.connection() as c:
            await c.execute(
                "UPDATE upstreams SET status=%s, last_error=%s, last_checked=%s WHERE slug=%s",
                (status, error, datetime.now(timezone.utc), slug))

    # ---------------- api keys ----------------

    # A key is live only if it is neither revoked nor past its expiry. Both
    # conditions live in this one predicate so no caller can forget either.
    _LIVE = "revoked_at IS NULL AND (expires_at IS NULL OR expires_at > now())"

    async def find_key_by_prefix(self, prefix: str) -> tuple[str, str, str] | None:
        """Return (name, key_hash, role) for a live key, or None."""
        async with self._pool.connection() as c:
            row = await (await c.execute(
                "SELECT name, key_hash, role FROM api_keys "
                "WHERE prefix=%s AND " + self._LIVE, (prefix,))).fetchone()
        return tuple(row) if row else None  # type: ignore[return-value]

    async def ensure_key(self, name: str, prefix: str, key_hash: str, role: str = "admin") -> None:
        async with self._pool.connection() as c:
            await c.execute(
                """INSERT INTO api_keys (name, prefix, key_hash, role) VALUES (%s,%s,%s,%s)
                   ON CONFLICT (prefix) DO UPDATE SET key_hash=EXCLUDED.key_hash,
                     role=EXCLUDED.role, revoked_at=NULL""",
                (name, prefix, key_hash, role))

    async def revoke_key(self, prefix: str) -> None:
        async with self._pool.connection() as c:
            await c.execute("UPDATE api_keys SET revoked_at=now() WHERE prefix=%s", (prefix,))

    # ---------------- users ----------------

    async def create_user(self, email: str, name: str, role: str,
                          password_hash: str | None = None) -> int:
        async with self._pool.connection() as c:
            row = await (await c.execute(
                """INSERT INTO users (email, name, role, password_hash)
                   VALUES (%s,%s,%s,%s)
                   ON CONFLICT (email) DO UPDATE SET name=EXCLUDED.name
                   RETURNING id""",
                (email.lower().strip(), name, role, password_hash))).fetchone()
        return int(row[0])

    async def get_user_by_email(self, email: str):
        async with self._pool.connection() as c:
            return await (await c.execute(
                """SELECT id, email, name, role, password_hash, disabled_at
                   FROM users WHERE email=%s""", (email.lower().strip(),))).fetchone()

    async def get_user(self, user_id: int):
        async with self._pool.connection() as c:
            return await (await c.execute(
                """SELECT id, email, name, role, password_hash, disabled_at
                   FROM users WHERE id=%s""", (user_id,))).fetchone()

    async def list_users(self) -> list[dict[str, Any]]:
        async with self._pool.connection() as c:
            rows = await (await c.execute(
                """SELECT id, email, name, role, created_at, disabled_at,
                          (password_hash IS NOT NULL) AS has_password
                   FROM users ORDER BY id""")).fetchall()
        return [{"id": r[0], "email": r[1], "name": r[2], "role": r[3],
                 "created_at": r[4].isoformat(), "disabled": r[5] is not None,
                 "has_password": r[6]} for r in rows]

    async def set_password(self, user_id: int, password_hash: str) -> None:
        async with self._pool.connection() as c:
            await c.execute("UPDATE users SET password_hash=%s WHERE id=%s",
                            (password_hash, user_id))

    # ---------------- invites ----------------

    async def create_invite(self, email: str, role: str, token_hash: str,
                            created_by: int | None, expires_at) -> int:
        async with self._pool.connection() as c:
            row = await (await c.execute(
                """INSERT INTO invites (email, role, token_hash, created_by, expires_at)
                   VALUES (%s,%s,%s,%s,%s) RETURNING id""",
                (email.lower().strip(), role, token_hash, created_by, expires_at))).fetchone()
        return int(row[0])

    async def find_invite(self, token_hash: str):
        async with self._pool.connection() as c:
            return await (await c.execute(
                """SELECT id, email, role, expires_at, consumed_at
                   FROM invites WHERE token_hash=%s""", (token_hash,))).fetchone()

    async def consume_invite(self, invite_id: int) -> bool:
        """Single-use, enforced in SQL. The WHERE clause makes a second
        concurrent accept a no-op rather than a race."""
        async with self._pool.connection() as c:
            cur = await c.execute(
                "UPDATE invites SET consumed_at=now() WHERE id=%s AND consumed_at IS NULL",
                (invite_id,))
        return cur.rowcount == 1

    async def list_invites(self) -> list[dict[str, Any]]:
        async with self._pool.connection() as c:
            rows = await (await c.execute(
                """SELECT id, email, role, created_at, expires_at, consumed_at
                   FROM invites ORDER BY id DESC""")).fetchall()
        return [{"id": r[0], "email": r[1], "role": r[2],
                 "created_at": r[3].isoformat(), "expires_at": r[4].isoformat(),
                 "consumed": r[5] is not None} for r in rows]

    # ---------------- sessions ----------------

    async def create_session(self, sid: str, user_id: int, expires_at) -> None:
        async with self._pool.connection() as c:
            await c.execute(
                "INSERT INTO sessions (id, user_id, expires_at) VALUES (%s,%s,%s)",
                (sid, user_id, expires_at))

    async def get_session(self, sid: str):
        async with self._pool.connection() as c:
            return await (await c.execute(
                """SELECT s.user_id, s.expires_at, u.email, u.name, u.role, u.disabled_at
                   FROM sessions s JOIN users u ON u.id = s.user_id
                   WHERE s.id=%s""", (sid,))).fetchone()

    async def delete_session(self, sid: str) -> None:
        async with self._pool.connection() as c:
            await c.execute("DELETE FROM sessions WHERE id=%s", (sid,))

    # ---------------- api keys, per user ----------------

    async def create_user_key(self, user_id: int, name: str, prefix: str,
                              key_hash: str, role: str, expires_at=None) -> int:
        async with self._pool.connection() as c:
            row = await (await c.execute(
                """INSERT INTO api_keys (name, prefix, key_hash, role, user_id, expires_at)
                   VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                (name, prefix, key_hash, role, user_id, expires_at))).fetchone()
        return int(row[0])

    async def delete_key_by_id(self, key_id: int) -> None:
        """Remove a key row outright.

        Only for the chat agent's per-turn key. A revoked row would be the
        honest record for a key a person held, but nobody ever held this one:
        it lives for one turn, and 200 turns a day would bury the real keys on
        the dashboard. The audit rows it produced stay, attributed to the user.
        """
        async with self._pool.connection() as c:
            await c.execute("DELETE FROM api_keys WHERE id=%s", (key_id,))

    async def list_keys_for_user(self, user_id: int) -> list[dict[str, Any]]:
        async with self._pool.connection() as c:
            rows = await (await c.execute(
                """SELECT id, name, prefix, created_at, revoked_at
                   FROM api_keys WHERE user_id=%s ORDER BY id DESC""", (user_id,))).fetchall()
        return [{"id": r[0], "name": r[1], "prefix": r[2],
                 "created_at": r[3].isoformat(), "revoked": r[4] is not None} for r in rows]

    async def list_all_keys(self) -> list[dict[str, Any]]:
        async with self._pool.connection() as c:
            rows = await (await c.execute(
                """SELECT k.id, k.name, k.prefix, k.created_at, k.revoked_at,
                          u.email
                   FROM api_keys k LEFT JOIN users u ON u.id = k.user_id
                   ORDER BY k.id DESC""")).fetchall()
        return [{"id": r[0], "name": r[1], "prefix": r[2],
                 "created_at": r[3].isoformat(), "revoked": r[4] is not None,
                 "owner": r[5] or "bootstrap"} for r in rows]

    async def key_owner(self, key_id: int) -> int | None:
        async with self._pool.connection() as c:
            row = await (await c.execute(
                "SELECT user_id FROM api_keys WHERE id=%s", (key_id,))).fetchone()
        return row[0] if row else None

    async def revoke_key_by_id(self, key_id: int) -> bool:
        async with self._pool.connection() as c:
            cur = await c.execute(
                "UPDATE api_keys SET revoked_at=now() WHERE id=%s AND revoked_at IS NULL",
                (key_id,))
        return cur.rowcount == 1

    async def find_key_with_user(self, prefix: str):
        """(name, key_hash, role, user_email) for a live key.

        The email is what the audit log is attributed to. Looking the key up
        WITHOUT it, which is what `find_key_by_prefix` does, leaves the audit
        row carrying the key's NAME: every user-created key defaults to the
        name "default", so A's and B's calls were indistinguishable.
        """
        async with self._pool.connection() as c:
            return await (await c.execute(
                """SELECT k.name, k.key_hash, k.role, u.email
                   FROM api_keys k LEFT JOIN users u ON u.id = k.user_id
                   WHERE k.prefix=%s AND """ + self._LIVE, (prefix,))).fetchone()

    # ---------------- audit ----------------

    async def audit(self, user_name: str, server_slug: str | None, tool: str | None,
                    duration_ms: int, outcome: str, detail: str | None = None,
                    tokens_in: int | None = None, tokens_out: int | None = None) -> None:
        async with self._pool.connection() as c:
            await c.execute(
                """INSERT INTO audit (user_name, server_slug, tool, duration_ms,
                                      outcome, detail, tokens_in, tokens_out)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (user_name, server_slug, tool, duration_ms, outcome, detail,
                 tokens_in, tokens_out))

    async def chat_turns_today(self) -> int:
        """Chat turns since local midnight, counted across ALL users.

        The cap protects one shared pool of API credits, so it is global by
        design, not per user. Every turn that reached the model is counted,
        failures included: a failed turn can still have been billed.
        """
        async with self._pool.connection() as c:
            row = await (await c.execute(
                """SELECT count(*) FROM audit
                   WHERE server_slug='chat' AND tool='turn'
                     AND ts >= date_trunc('day', now())""")).fetchone()
        return int(row[0])

    async def recent_audit(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self._pool.connection() as c:
            rows = await (await c.execute(
                """SELECT ts, user_name, server_slug, tool, duration_ms, outcome, detail,
                          tokens_in, tokens_out
                   FROM audit ORDER BY ts DESC LIMIT %s""", (limit,))).fetchall()
        return [
            {"ts": r[0].isoformat(), "user": r[1], "server": r[2], "tool": r[3],
             "duration_ms": r[4], "outcome": r[5], "detail": r[6],
             "tokens_in": r[7], "tokens_out": r[8]}
            for r in rows
        ]
