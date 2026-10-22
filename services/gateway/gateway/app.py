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
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from starlette.responses import JSONResponse

from . import apikeys, chat, proxy, web
from .config import Config
from .crypto import Crypto
from .db import Db, Upstream
from .upstreams import CONNECTED, DISABLED, UNREACHABLE, UpstreamError, call_tool, fetch_all

log = logging.getLogger("gateway")

# Who is making the current request. Set by the auth middleware, read by the
# audit write, so the proxy sink does not have to thread it through.
current_user: contextvars.ContextVar[str] = contextvars.ContextVar("current_user", default="anonymous")

REFRESH_MAX_AGE = float(os.environ.get("REFRESH_MAX_AGE_SECONDS", "3"))
# How stale the Servers page is allowed to be, in seconds. 0 means refresh on
# every read.
#
# The page reads the stored status, which only a refresh writes, so without
# this it sat a whole health-loop cycle behind what /mcp was already serving:
# during the DOD-10 outage it still said Connected while clients had correctly
# dropped to the two fx tools, and said Unreachable after recovery while all
# seven were back. Clients were never wrong; the page was.
#
# Why 0 and not 5. Kapardhi asked for a 5 second cache AND for the page to
# show Unreachable within one page load. Those conflict: with any cache at
# all, the first load after a failure can fall inside the window and return
# the old status, which is exactly what 5 did when measured (3 loads, about
# 6 seconds). The cache was there to stop a page load costing a fan-out, and
# the measurement says that worry does not survive contact with the numbers:
# a cached load is ~3 ms and a load that fans out is ~150 ms, while the
# Servers tab polls every 5 seconds, so refreshing on every read produces the
# SAME one-fan-out-per-5-seconds that a 5 second cache produces. The cache
# bought nothing and cost correctness. Set STATUS_MAX_AGE_SECONDS=5 to get it
# back.
STATUS_MAX_AGE = float(os.environ.get("STATUS_MAX_AGE_SECONDS", "0"))


class Gateway:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.db = Db(cfg.database_url)
        self.crypto = Crypto(cfg.encryption_key)
        self.mcp = MCPServer("gateway", version="0.1.0")
        # public tool name -> (slug, schema fingerprint). The fingerprint is
        # what makes a CHANGED upstream schema propagate: keying on the name
        # alone meant a tool whose schema changed under the same name was
        # skipped forever. Observed when woo-mcp added an enum to `status`
        # and the gateway kept serving the old bare string.
        self._registered: dict[str, tuple[str, str]] = {}
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

    async def refresh(self, force: bool = False, max_age: float | None = None) -> None:
        """Rebuild the served tool list from the live upstreams.

        Called before each MCP request when the cache is older than
        REFRESH_MAX_AGE, and by the background health loop. That is what makes
        a killed upstream disappear from tools/list promptly (GW-5) and a
        registry flag take effect (GW-6) without waiting for the slow loop.
        """
        async with self._lock:
            age = REFRESH_MAX_AGE if max_age is None else max_age
            if not force and (time.monotonic() - self._last_refresh) < age:
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

            def fingerprint(schema: dict) -> str:
                # sort_keys so an unordered dict does not look like a change
                return json.dumps(schema, sort_keys=True)

            desired: dict[str, tuple[str, dict, str]] = {}
            for name, (slug, up) in wanted.items():
                schema = getattr(up, "input_schema", None) or {"type": "object", "properties": {}}
                desired[name] = (slug, schema,
                                 "[%s] %s" % (slug, getattr(up, "description", "") or ""))

            # Drop anything gone, and anything whose schema changed: the SDK
            # derives its argument validator from the synthesised signature,
            # so a changed schema needs a rebuilt function, not a patched
            # `parameters`.
            for name, (slug, fp) in list(self._registered.items()):
                if name not in desired or fingerprint(desired[name][1]) != fp:
                    self.mcp.remove_tool(name)
                    self._registered.pop(name, None)

            for name, (slug, schema, description) in desired.items():
                if name in self._registered:
                    continue
                fn = proxy.build_proxy_fn(name, schema, self._sink)
                self.mcp.add_tool(fn, name=name, description=description)
                # Pin the upstream's exact schema; the derived one is lossy.
                self.mcp._tool_manager.get_tool(name).parameters = schema
                self._registered[name] = (slug, fingerprint(schema))

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
            # WWW-Authenticate tells a client HOW to authenticate. Without
            # it, MCP Inspector met our bare 401 and fell back to OAuth
            # Dynamic Client Registration, then reported
            # "Dynamic Client Registration rejected (HTTP 401)" -- an error
            # naming OAuth when the real cause was an empty bearer token.
            # RFC 6750 section 3.
            resp = JSONResponse(
                {"error": "unauthorized",
                 "detail": "send a gateway API key as: Authorization: Bearer gw_<prefix>_<secret>"},
                status_code=401,
                headers={
                    "WWW-Authenticate":
                        'Bearer realm="mcp-gateway", error="invalid_token", '
                        'error_description="missing or invalid gateway API key"'
                },
            )
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
    """Return the audit identity behind a presented key, or None.

    The identity is the owning user's EMAIL where the key has an owner, and
    the key's name only for the ownerless bootstrap key. This matters: every
    key a user creates in the dashboard is named "default" unless they rename
    it, so attributing audit rows to the key name made A's calls and B's
    calls both read "default". DOD-06 and DOD-11 ask who made each call, and
    the answer has to be a person.
    """
    prefix = apikeys.prefix_of(token)
    if not prefix:
        return None
    row = await gw.db.find_key_with_user(prefix)
    if not row:
        return None
    name, key_hash, _role, email = row
    if not apikeys.verify(token, key_hash):
        return None
    return email or name


# -------------------------------------------------------------- app

def chat_config(cfg: Config) -> chat.ChatConfig:
    """The chat agent's settings, including how it reaches its own /mcp.

    Loopback, not the Service name: the agent is a client of THIS process, so
    going out to the Service would add a hop that could land on a different
    replica mid-turn.
    """
    port = os.environ.get("PORT", "8080")
    return chat.ChatConfig(
        provider=cfg.llm_provider,
        model=cfg.llm_model,
        api_key=cfg.llm_api_key,
        effort=cfg.llm_effort,
        max_steps=cfg.chat_max_steps,
        max_tokens=cfg.chat_max_tokens,
        daily_cap=cfg.chat_daily_cap,
        max_question_chars=cfg.chat_max_question_chars,
        max_tool_result_chars=cfg.chat_max_tool_result_chars,
        self_mcp_url=os.environ.get(
            "GATEWAY_SELF_MCP_URL", "http://127.0.0.1:%s/mcp" % port),
        tool_timeout_seconds=cfg.upstream_timeout_seconds * 2,
    )


def build_app() -> FastAPI:
    cfg = Config.from_env()
    gw = Gateway(cfg)
    gw.agent = chat.Agent(gw, chat_config(cfg))

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
        # Refresh before reading, so the page cannot disagree with what
        # /mcp is serving. force=True when STATUS_MAX_AGE is 0, because a
        # zero max_age still short-circuits on an identical monotonic clock
        # reading, which is reachable at this speed.
        await gw.refresh(force=STATUS_MAX_AGE <= 0, max_age=STATUS_MAX_AGE)
        # Never returns credential_enc, nor the decrypted value. The page
        # gets a boolean and nothing more.
        by_slug: dict[str, list[str]] = {}
        for tool_name, (slug, _fp) in gw._registered.items():
            by_slug.setdefault(slug, []).append(tool_name)
        return [
            {"slug": u.slug, "url": u.url, "enabled": u.enabled,
             "status": u.status, "last_error": u.last_error,
             "has_credential": bool(u.credential_enc),
             "tools": sorted(by_slug.get(u.slug, []))}
            for u in await gw.db.list_upstreams()
        ]

    @api.get("/admin/audit")
    async def admin_audit(limit: int = 50) -> list[dict[str, Any]]:
        return await gw.db.recent_audit(limit)

    # Dashboard auth, invites, members and keys. Mounted before the catch-all
    # MCP mount below so these paths win.
    web.install_error_handler(api)
    api.include_router(web.build_router(gw))

    # Dashboard. Static assets, then the SPA shell on the two page routes.
    _static = os.path.join(os.path.dirname(__file__), "static")
    api.mount("/static", StaticFiles(directory=_static), name="static")

    @api.get("/")
    async def index() -> FileResponse:
        return FileResponse(os.path.join(_static, "index.html"))

    @api.get("/accept")
    async def accept_page() -> FileResponse:
        # Same shell; the page reads ?token= itself. The token is never
        # sent to the server by this GET, only by the POST that uses it.
        return FileResponse(os.path.join(_static, "index.html"))

    # Mounted at "/" so the MCP endpoint is exactly /mcp with no redirect.
    # FastAPI matches routes in order and these are registered first, so
    # /healthz, /readyz and /admin/* still win.
    api.mount("/", auth_middleware(mcp_app, gw))
    api.state.gateway = gw
    return api


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    import uvicorn

    # FORWARDED_ALLOW_IPS decides whether X-Forwarded-Proto is believed.
    #
    # Behind an ingress controller that terminates TLS, the pod is reached
    # over plain HTTP, so `request.url.scheme` is "http" and the session
    # cookie's Secure flag never turns on, however correct the conditional
    # is. uvicorn parses the forwarded headers only for clients listed here,
    # and the default is 127.0.0.1, which the ingress controller is not.
    #
    # Empty by default, so a local run trusts nothing and behaves exactly as
    # it does today. Prod sets "*", which is safe in this topology for two
    # reasons: the gateway Service is ClusterIP with no route from outside,
    # and the only thing a spoofed X-Forwarded-Proto: https can do is make
    # the cookie MORE restrictive. See VDOD-8 and SEC-2.
    forwarded = os.environ.get("FORWARDED_ALLOW_IPS", "").strip()
    kwargs: dict[str, Any] = {}
    if forwarded:
        kwargs["proxy_headers"] = True
        kwargs["forwarded_allow_ips"] = forwarded

    uvicorn.run(build_app(), host="0.0.0.0",
                port=int(os.environ.get("PORT", "8080")),
                log_level="warning", **kwargs)


if __name__ == "__main__":
    main()
