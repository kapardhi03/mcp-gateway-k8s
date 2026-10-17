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

CREATE TABLE IF NOT EXISTS api_keys (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    prefix      TEXT NOT NULL UNIQUE,
    key_hash    TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'admin',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at  TIMESTAMPTZ
);

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

    async def find_key_by_prefix(self, prefix: str) -> tuple[str, str, str] | None:
        """Return (name, key_hash, role) for a live key, or None."""
        async with self._pool.connection() as c:
            row = await (await c.execute(
                "SELECT name, key_hash, role FROM api_keys WHERE prefix=%s AND revoked_at IS NULL",
                (prefix,))).fetchone()
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

    # ---------------- audit ----------------

    async def audit(self, user_name: str, server_slug: str | None, tool: str | None,
                    duration_ms: int, outcome: str, detail: str | None = None) -> None:
        async with self._pool.connection() as c:
            await c.execute(
                """INSERT INTO audit (user_name, server_slug, tool, duration_ms, outcome, detail)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (user_name, server_slug, tool, duration_ms, outcome, detail))

    async def recent_audit(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self._pool.connection() as c:
            rows = await (await c.execute(
                """SELECT ts, user_name, server_slug, tool, duration_ms, outcome, detail
                   FROM audit ORDER BY ts DESC LIMIT %s""", (limit,))).fetchall()
        return [
            {"ts": r[0].isoformat(), "user": r[1], "server": r[2], "tool": r[3],
             "duration_ms": r[4], "outcome": r[5], "detail": r[6]}
            for r in rows
        ]
