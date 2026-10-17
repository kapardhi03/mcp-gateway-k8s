"""Talking to upstream MCP servers: fan-out, timeouts, health.

Two rules shape everything here.

1. A slow or dead upstream must never break `tools/list`. Each upstream is
   given its own timeout and its own task; whatever it does, the others are
   still returned. A failing upstream contributes no tools and is marked
   Unreachable.
2. An upstream credential must never escape. It is decrypted only to build
   the outbound header and is never put in a log line, an error message or a
   returned value. Errors carry the slug and the exception TYPE, never the
   exception text, because a transport error can quote the request including
   its headers.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx2 as httpx
from mcp.client import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .crypto import Crypto
from .db import Upstream

log = logging.getLogger("gateway.upstreams")

CONNECTED = "Connected"
UNREACHABLE = "Unreachable"
DISABLED = "Disabled"


@dataclass
class UpstreamTools:
    slug: str
    status: str
    tools: list[Any] = field(default_factory=list)
    error: str | None = None


def auth_headers(u: Upstream, crypto: Crypto) -> dict[str, str]:
    """Build the outbound auth header for one upstream, or {} if it has none.

    Kept tiny and pure so it can be tested without a network: GW-8 asserts the
    credential appears here and nowhere else.
    """
    if not u.credential_enc or not u.auth_header:
        return {}
    secret = crypto.decrypt(u.credential_enc)
    value = "%s %s" % (u.auth_scheme, secret) if u.auth_scheme else secret
    return {u.auth_header: value}


@asynccontextmanager
async def _session(u: Upstream, crypto: Crypto, timeout: float):
    """One MCP session to one upstream.

    streamable_http_client's `http_client` argument is the SDK's documented
    hook for custom headers; StreamableHTTPTransport itself takes none.
    """
    headers = auth_headers(u, crypto)
    async with httpx.AsyncClient(headers=headers, timeout=timeout) as hc:
        async with streamable_http_client(u.url, http_client=hc) as streams:
            read, write = streams[0], streams[1]
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


async def fetch_tools(u: Upstream, crypto: Crypto, timeout: float) -> UpstreamTools:
    """List one upstream's tools. Never raises."""
    if not u.enabled:
        return UpstreamTools(u.slug, DISABLED)
    try:
        async with asyncio.timeout(timeout):
            async with _session(u, crypto, timeout) as s:
                result = await s.list_tools()
        return UpstreamTools(u.slug, CONNECTED, list(result.tools))
    except TimeoutError:
        return UpstreamTools(u.slug, UNREACHABLE, [], "timed out after %.1fs" % timeout)
    except Exception as exc:
        # Type only. The text of a transport error can echo request headers.
        return UpstreamTools(u.slug, UNREACHABLE, [], type(exc).__name__)


async def fetch_all(upstreams: list[Upstream], crypto: Crypto,
                    timeout: float) -> list[UpstreamTools]:
    """Concurrent fan-out. One slow upstream costs `timeout`, not N x timeout."""
    if not upstreams:
        return []
    return list(await asyncio.gather(
        *(fetch_tools(u, crypto, timeout) for u in upstreams)))


async def call_tool(u: Upstream, crypto: Crypto, timeout: float,
                    tool: str, arguments: dict[str, Any]) -> Any:
    """Route one call to one upstream. Raises UpstreamError on any failure."""
    try:
        async with asyncio.timeout(timeout):
            async with _session(u, crypto, timeout) as s:
                return await s.call_tool(tool, arguments)
    except TimeoutError as exc:
        raise UpstreamError(
            "upstream %r did not respond within %.1fs" % (u.slug, timeout)) from exc
    except Exception as exc:
        raise UpstreamError(
            "upstream %r failed: %s" % (u.slug, type(exc).__name__)) from exc


class UpstreamError(RuntimeError):
    """A call to an upstream failed. Message is safe to show a model."""
