"""FX MCP server. Two tools over Streamable HTTP.

Second in-cluster upstream for the gateway (D-010). Backed by Frankfurter,
which serves ECB reference rates with no API key: verified 2026-10-17 by
calling it with no Authorization header and getting HTTP 200.

No credentials anywhere in this service. That is the point of the pairing:
woo-mcp exercises the credential path, fx-mcp exercises the "upstream with no
auth" path, and the gateway has to handle both.
"""

from __future__ import annotations

import functools
import logging
import os
import re
from typing import Any

import httpx2 as httpx
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

log = logging.getLogger("fx-mcp")

mcp = MCPServer("fx-mcp", version="0.1.0")

API_BASE = os.environ.get("FX_API_BASE", "https://api.frankfurter.dev/v1").rstrip("/")
TIMEOUT = float(os.environ.get("FX_TIMEOUT_SECONDS", "10"))

_transport: Any = None


def set_transport(t: Any) -> None:
    """Test seam: inject a MockTransport so tests never touch the network."""
    global _transport
    _transport = t


class FxError(RuntimeError):
    """An anticipated failure talking to the rates API."""


def surfaced(fn):
    """Convert FxError to the SDK's ToolError so the model can read it.

    Same reasoning as woo-mcp: the SDK withholds the message of any exception
    that is not its own ToolError and reports a bare crash instead.
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except FxError as exc:
            raise ToolError(str(exc)) from exc

    return wrapper


def _get(path: str, params: dict[str, str]) -> dict[str, Any]:
    url = "%s%s" % (API_BASE, path)
    try:
        with httpx.Client(timeout=TIMEOUT, transport=_transport) as c:
            r = c.get(url, params=params)
    except httpx.TimeoutException as exc:
        raise FxError(
            "the rates service did not respond within %.1fs (GET %s)" % (TIMEOUT, path)
        ) from exc
    except httpx.HTTPError as exc:
        raise FxError(
            "could not reach the rates service at %s (GET %s): %s"
            % (API_BASE, path, type(exc).__name__)
        ) from exc

    if r.status_code >= 400:
        raise FxError(
            "the rates service rejected GET %s with HTTP %d: %s"
            % (path, r.status_code, r.text[:160])
        )
    try:
        return r.json()
    except Exception as exc:
        raise FxError("the rates service returned a non-JSON response to GET %s" % path) from exc


def _code(value: str, field: str) -> str:
    v = (value or "").strip().upper()
    if len(v) != 3 or not v.isalpha():
        raise FxError("%s must be a 3-letter currency code, got %r" % (field, value))
    return v


def _fetch_rates(base: str, symbols: str | None, date: str | None) -> dict[str, Any]:
    """Shared by both tools.

    Deliberately a plain function rather than calling the decorated `rates`
    tool: reaching through a decorator (`rates.__wrapped__`) would couple this
    to how the SDK wraps tools, which is not ours to depend on.
    """
    b = _code(base, "base")
    params: dict[str, str] = {"base": b}
    if symbols:
        params["symbols"] = ",".join(_code(s, "symbols") for s in symbols.split(","))
    if date:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            raise FxError("date must be YYYY-MM-DD, got %r" % date)
    path = "/%s" % date if date else "/latest"
    data = _get(path, params)
    return {"base": data.get("base"), "date": data.get("date"), "rates": data.get("rates", {})}


@mcp.tool()
@surfaced
def rates(base: str = "USD", symbols: str | None = None, date: str | None = None) -> dict[str, Any]:
    """Current or historical exchange rates.

    base: 3-letter currency code to quote against, for example "USD".
    symbols: optional comma-separated codes to limit the result, e.g. "EUR,GBP".
    date: optional YYYY-MM-DD for a historical rate. Omit for the latest.
    """
    return _fetch_rates(base, symbols, date)


@mcp.tool()
@surfaced
def convert(amount: float, from_currency: str, to_currency: str, date: str | None = None) -> dict[str, Any]:
    """Convert an amount between two currencies.

    amount: the amount to convert, must be zero or more.
    from_currency: 3-letter source code, for example "USD".
    to_currency: 3-letter target code, for example "EUR".
    date: optional YYYY-MM-DD to convert at a historical rate.
    """
    if amount < 0:
        raise FxError("amount must be zero or more, got %r" % amount)
    src = _code(from_currency, "from_currency")
    dst = _code(to_currency, "to_currency")
    if src == dst:
        return {"amount": amount, "from": src, "to": dst, "rate": 1.0,
                "converted": round(amount, 2), "date": date or "n/a"}

    out = _fetch_rates(src, dst, date)
    rate = (out.get("rates") or {}).get(dst)
    if rate is None:
        raise FxError("no rate available for %s to %s on %s" % (src, dst, out.get("date")))
    return {
        "amount": amount,
        "from": src,
        "to": dst,
        "rate": rate,
        "converted": round(amount * float(rate), 2),
        "date": out.get("date"),
    }


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    log.info("fx-mcp starting: api_base=%s timeout=%.1fs", API_BASE, TIMEOUT)
    import uvicorn

    app = mcp.streamable_http_app(streamable_http_path="/mcp", host="0.0.0.0")
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), log_level="warning")


if __name__ == "__main__":
    main()
