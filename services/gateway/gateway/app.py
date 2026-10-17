"""The gateway: MCP server to clients, MCP client to every upstream.

Shape:
  FastAPI  ->  /healthz, /readyz, /admin/*   (plain HTTP)
           ->  /mcp  (the SDK's Streamable HTTP app, behind auth middleware)

Auth, phase 1: one bootstrap admin API key from a Secret, stored hashed
(D-013 option A). Team features are phase 2.

Audit: every tool call writes a row with user, server, tool, timestamp,
duration_ms and outcome. Rejected calls are audited too, and never reach an
upstream.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from starlette.responses import JSONResponse

from . import apikeys, proxy
from .config import Config
from .crypto import Crypto
from .db import Db, Upstream
from .upstreams import CONNECTED, DISABLED, UNREACHABLE, UpstreamError, call_tool, fetch_all

log = logging.getLogger("gateway")

# Who is making the current request. Set by the auth middleware, read by the
# audit write, so the proxy sink does not have to thread it through.
current_user: contextvars.ContextVar[str] = contextvars.ContextVar("current_user", default="anonymous")

REFRESH_MAX_AGE = float(os.environ.get("REFRESH_MAX_AGE_SECONDS", "3"))


class Gateway:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.db = Db(cfg.database_url)
        self.crypto = Crypto(cfg.encryption_key)
        self.mcp = MCPServer("gateway", version="0.1.0")
        self._registered: dict[str, str] = {}   # public tool name -> slug
        self._by_slug: dict[str, Upstream] = {}
        self._last_refresh = 0.0
        self._lock = asyncio.Lock()

    # ---------------------------------------------------------- lifecycle

    async def start(self) -> None:
        await self.db.open()
        await self._seed()
        await self.refresh(force=True)

    async def _seed(self) -> None:
        """Bootstrap key and the in-cluster upstreams, both idempotent."""
        full = self.cfg.bootstrap_api_key
        prefix = apikeys.prefix_of(full)
        if not prefix:
            raise RuntimeError(
                "BOOTSTRAP_API_KEY is malformed. Expected gw_<8 hex>_<secret>.")
        await self.db.ensure_key("bootstrap-admin", prefix, apikeys.hash_key(full), "admin")

        for slug, env in (("woo", "WOO_MCP_URL"), ("fx", "FX_MCP_URL")):
            url = os.environ.get(env, "").strip()
            if url:
                await self.db.upsert_upstream(slug, url, None, None, None, True)

    # ---------------------------------------------------------- registry

    async def refresh(self, force: bool = False) -> None:
        """Rebuild the served tool list from the live upstreams.

        Called before each MCP request when the cache is older than
        REFRESH_MAX_AGE, and by the background health loop. That is what makes
        a killed upstream disappear from tools/list promptly (GW-5) and a
        registry flag take effect (GW-6) without waiting for the slow loop.
        """
        async with self._lock:
            if not force and (time.monotonic() - self._last_refresh) < REFRESH_MAX_AGE:
                return
            rows = await self.db.list_upstreams()
            self._by_slug = {u.slug: u for u in rows}
            results = await fetch_all(
                [u for u in rows if u.enabled], self.crypto, self.cfg.upstream_timeout_seconds)

            wanted: dict[str, tuple[str, Any]] = {}
            for r in results:
                await self.db.set_status(r.slug, r.status, r.error)
                if r.status != CONNECTED:
                    continue
                for t in r.tools:
                    wanted[proxy.qualified(r.slug, t.name)] = (r.slug, t)
            for u in rows:
                if not u.enabled:
                    await self.db.set_status(u.slug, DISABLED, None)

            for name in list(self._registered):
                if name not in wanted:
                    self.mcp.remove_tool(name)
                    self._registered.pop(name, None)

            for name, (slug, t) in wanted.items():
                if name in self._registered:
                    continue
                schema = getattr(t, "input_schema", None) or {"type": "object", "properties": {}}
                fn = proxy.build_proxy_fn(name, schema, self._sink)
                self.mcp.add_tool(
                    fn, name=name,
                    description="[%s] %s" % (slug, getattr(t, "description", "") or ""))
                # Pin the upstream's exact schema; the derived one is lossy.
                self.mcp._tool_manager.get_tool(name).parameters = schema
                self._registered[name] = slug

            self._last_refresh = time.monotonic()

    # ---------------------------------------------------------- routing

    async def _sink(self, public_name: str, arguments: dict[str, Any]) -> Any:
        """Route one proxied call, time it, and audit it. Always audits."""
        user = current_user.get()
        parts = proxy.split(public_name)
        slug, tool = parts if parts else ("unknown", public_name)
        started = time.monotonic()
        outcome, detail = "error", None
        try:
            u = self._by_slug.get(slug)
            if u is None:
                raise UpstreamError("no upstream registered with slug %r" % slug)
            if not u.enabled:
                raise UpstreamError("upstream %r is disabled" % slug)
            result = await call_tool(
                u, self.crypto, self.cfg.upstream_timeout_seconds, tool, arguments)
            outcome = "ok"
            return _unwrap(result)
        except UpstreamError as exc:
            detail = str(exc)
            raise ToolError(str(exc)) from exc
        except Exception as exc:
            detail = type(exc).__name__
            raise ToolError("gateway failed calling %s: %s" % (public_name, type(exc).__name__)) from exc
        finally:
            ms = int((time.monotonic() - started) * 1000)
            try:
                await self.db.audit(user, slug, tool, ms, outcome, detail)
            except Exception:
                log.exception("audit write failed for %s", public_name)

    # ---------------------------------------------------------- health

    async def health_loop(self) -> None:
        while True:
            try:
                await self.refresh(force=True)
            except Exception:
                log.exception("health refresh failed")
            await asyncio.sleep(self.cfg.health_interval_seconds)


def _unwrap(result: Any) -> Any:
    """Return the upstream's content as plain data, not SDK objects."""
    out = []
    for c in getattr(result, "content", []) or []:
        text = getattr(c, "text", None)
        if text is None:
            continue
        try:
            out.append(json.loads(text))
        except Exception:
            out.append(text)
    if len(out) == 1:
        return out[0]
    return out


# -------------------------------------------------------------- ASGI auth

def auth_middleware(app, gw: "Gateway"):
    """Authenticate, then refresh, then hand off.

    A rejected request is audited and never reaches an upstream.
    """

    async def wrapped(scope, receive, send):
        if scope["type"] != "http":
            await app(scope, receive, send)
            return

        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        raw = headers.get("authorization", "")
        token = raw[7:].strip() if raw.lower().startswith("bearer ") else ""

        user = await _authenticate(gw, token)
        if user is None:
            await gw.db.audit("anonymous", None, None, 0, "rejected",
                              "missing or invalid API key")
            resp = JSONResponse({"error": "unauthorized"}, status_code=401)
            await resp(scope, receive, send)
            return

        tok = current_user.set(user)
        try:
            await gw.refresh()
            await app(scope, receive, send)
        finally:
            current_user.reset(tok)

    return wrapped


async def _authenticate(gw: "Gateway", token: str) -> str | None:
    prefix = apikeys.prefix_of(token)
    if not prefix:
        return None
    row = await gw.db.find_key_by_prefix(prefix)
    if not row:
        return None
    name, key_hash, _role = row
    return name if apikeys.verify(token, key_hash) else None


# -------------------------------------------------------------- app

def build_app() -> FastAPI:
    cfg = Config.from_env()
    gw = Gateway(cfg)

    # The SDK's Streamable HTTP app carries its own lifespan, which starts the
    # session manager's task group. Mounting it inside FastAPI does NOT run
    # that lifespan, and every request then dies with "Task group is not
    # initialized". So the session manager is entered explicitly here.
    mcp_app = gw.mcp.streamable_http_app(streamable_http_path="/mcp", host="0.0.0.0")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        log.info("gateway starting: %s", cfg.redacted())
        async with gw.mcp.session_manager.run():
            await gw.start()
            task = asyncio.create_task(gw.health_loop())
            try:
                yield
            finally:
                task.cancel()
                await gw.db.close()

    api = FastAPI(title="mcp-gateway", version="0.1.0", lifespan=lifespan)

    @api.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @api.get("/readyz")
    async def readyz() -> dict[str, Any]:
        return {"status": "ok", "tools": len(gw._registered)}

    @api.get("/admin/upstreams")
    async def admin_upstreams() -> list[dict[str, Any]]:
        # Never returns credential_enc. Not even encrypted.
        return [
            {"slug": u.slug, "url": u.url, "enabled": u.enabled,
             "status": u.status, "last_error": u.last_error,
             "has_credential": bool(u.credential_enc)}
            for u in await gw.db.list_upstreams()
        ]

    @api.get("/admin/audit")
    async def admin_audit(limit: int = 50) -> list[dict[str, Any]]:
        return await gw.db.recent_audit(limit)

    # Mounted at "/" so the MCP endpoint is exactly /mcp with no redirect.
    # FastAPI matches routes in order and these are registered first, so
    # /healthz, /readyz and /admin/* still win.
    api.mount("/", auth_middleware(mcp_app, gw))
    api.state.gateway = gw
    return api


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    import uvicorn

    uvicorn.run(build_app(), host="0.0.0.0",
                port=int(os.environ.get("PORT", "8080")), log_level="warning")


if __name__ == "__main__":
    main()
