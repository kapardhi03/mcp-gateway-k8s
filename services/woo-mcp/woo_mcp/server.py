"""The WooCommerce MCP server. Five tools over Streamable HTTP.

Written for this repo, not installed from anywhere (W-01). Protocol handling
follows the D-001 spike: one SDK 2.3.0 server serves both 2026-07-28 and
2025-11-25 clients with no special handling.
"""

from __future__ import annotations

import functools
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .config import Config
from .woo import WooClient, WooError

log = logging.getLogger("woo-mcp")


def surfaced(fn):
    """Turn a WooError into the SDK's ToolError so the model can read it.

    The SDK only puts a message in front of the model when a tool raises its
    own ToolError. Any other exception is treated as a crash: the model sees
    "Error executing tool <name>" and the text is withheld. WooError describes
    anticipated failures, a dead store or a 401, which are exactly the things
    the caller needs to read, so convert at the MCP boundary.

    This keeps woo.py free of any SDK import. WM-8 regression-tests it.
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except WooError as exc:
            raise ToolError(str(exc)) from exc

    return wrapper

mcp = MCPServer("woo-mcp", version="0.1.0")

# Defined HERE, above every tool, not next to the validation that uses it.
# `from __future__ import annotations` makes annotations strings, and
# @mcp.tool() evaluates them when the function is DEFINED. A Literal declared
# below the first tool that references it raises
# "InvalidSignature: Unable to evaluate type annotations" at import, which
# py_compile does not catch because compiling never evaluates annotations.
#
# Literal rather than str so the eight valid values reach the tool's JSON
# schema as an enum. Without it a model learns them only by guessing and
# being rejected: the validation below still rejects a bad value, but the
# model never sees the list.
OrderStatus = Literal[
    "pending", "processing", "on-hold", "completed",
    "cancelled", "refunded", "failed", "trash",
]
VALID_STATUSES = (
    "pending", "processing", "on-hold", "completed",
    "cancelled", "refunded", "failed", "trash",
)

_client: WooClient | None = None


def client() -> WooClient:
    global _client
    if _client is None:
        _client = WooClient(Config.from_env())
    return _client


def set_client(c: WooClient) -> None:
    """Test seam."""
    global _client
    _client = c


# ---------------------------------------------------------------- helpers

def _day_bounds(tz_name: str, day: str | None) -> tuple[str, str]:
    """Return (after, before) ISO timestamps bounding one day in the store's tz.

    'today' is resolved in the STORE's timezone, not UTC. The Definition of
    Done asks "what orders came in today", and on a store east or west of UTC
    those are different sets of orders for several hours a day.
    """
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo("UTC")

    if day is None or day == "today":
        local_now = datetime.now(tz)
        start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        try:
            parsed = datetime.strptime(day, "%Y-%m-%d")
        except ValueError as exc:
            raise WooError(
                "date must be 'today' or YYYY-MM-DD, got %r" % day
            ) from exc
        start = parsed.replace(tzinfo=tz)

    end = start + timedelta(days=1)
    # WooCommerce compares these against post_date_gmt, so send UTC.
    return (
        start.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S"),
        end.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S"),
    )


def _product_summary(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": p.get("id"),
        "name": p.get("name"),
        "sku": p.get("sku"),
        "price": p.get("price"),
        "status": p.get("status"),
        "permalink": p.get("permalink"),
    }


def _order_summary(o: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": o.get("id"),
        "status": o.get("status"),
        "total": o.get("total"),
        "currency": o.get("currency"),
        "payment_method": o.get("payment_method"),
        "date_created": o.get("date_created"),
        "line_items": [
            {"name": li.get("name"), "quantity": li.get("quantity"), "sku": li.get("sku")}
            for li in (o.get("line_items") or [])
        ],
    }


# ---------------------------------------------------------------- tools

@mcp.tool()
@surfaced
def list_products(search: str | None = None, per_page: int = 20) -> list[dict[str, Any]]:
    """List products in the store.

    search: optional text to match against product names.
    per_page: how many to return, 1 to 100.
    """
    if not 1 <= per_page <= 100:
        raise WooError("per_page must be between 1 and 100, got %d" % per_page)
    q: dict[str, str] = {"per_page": str(per_page)}
    if search:
        q["search"] = search
    return [_product_summary(p) for p in client().get("/wp-json/wc/v3/products", q)]


@mcp.tool()
@surfaced
def create_product(
    name: str,
    regular_price: str,
    sku: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a simple published product.

    name: the product name, required.
    regular_price: price as a decimal string, for example "9.99".
    sku: optional stock keeping unit.
    description: optional long description.
    """
    if not name.strip():
        raise WooError("name must not be empty")
    try:
        if float(regular_price) < 0:
            raise ValueError
    except ValueError as exc:
        raise WooError(
            "regular_price must be a non-negative decimal string, got %r" % regular_price
        ) from exc

    body: dict[str, Any] = {
        "name": name,
        "type": "simple",
        "regular_price": regular_price,
        "status": "publish",
    }
    if sku:
        body["sku"] = sku
    if description:
        body["description"] = description
    return _product_summary(client().post("/wp-json/wc/v3/products", body))


@mcp.tool()
@surfaced
def list_orders(status: OrderStatus | None = None, date: str | None = None) -> list[dict[str, Any]]:
    """List orders, newest first.

    status: optional WooCommerce status, for example "processing" or "completed".
    date: "today" or YYYY-MM-DD. Resolved in the STORE's timezone, not UTC.
    """
    q: dict[str, str] = {"per_page": "100", "orderby": "date", "order": "desc"}
    if status:
        q["status"] = status
    if date is not None:
        after, before = _day_bounds(client().store_timezone(), date)
        q["after"] = after
        q["before"] = before
    return [_order_summary(o) for o in client().get("/wp-json/wc/v3/orders", q)]


@mcp.tool()
@surfaced
def get_order(order_id: int) -> dict[str, Any]:
    """Fetch one order by its numeric id."""
    if order_id <= 0:
        raise WooError("order_id must be a positive integer, got %r" % order_id)
    return _order_summary(client().get("/wp-json/wc/v3/orders/%d" % order_id))


@mcp.tool()
@surfaced
def update_order_status(order_id: int, status: OrderStatus) -> dict[str, Any]:
    """Change one order's status.

    order_id: the numeric order id.
    status: one of pending, processing, on-hold, completed, cancelled,
            refunded, failed, trash.
    """
    if order_id <= 0:
        raise WooError("order_id must be a positive integer, got %r" % order_id)
    if status not in VALID_STATUSES:
        raise WooError(
            "status must be one of %s, got %r" % (", ".join(VALID_STATUSES), status)
        )
    return _order_summary(
        client().put("/wp-json/wc/v3/orders/%d" % order_id, {"status": status})
    )


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    cfg = Config.from_env()
    log.info("woo-mcp starting: %s", cfg.redacted())
    import uvicorn

    app = mcp.streamable_http_app(streamable_http_path="/mcp", host="0.0.0.0")
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), log_level="warning")


if __name__ == "__main__":
    main()
