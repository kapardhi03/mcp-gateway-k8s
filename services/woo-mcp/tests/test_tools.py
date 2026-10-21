"""Tool tests against a mocked WooCommerce API. No network, no cluster."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx2 as httpx
import pytest

from mcp.server.mcpserver.exceptions import ToolError

from woo_mcp import server
from woo_mcp.config import Config
from woo_mcp.woo import WooClient, WooError

HOME = "http://store.localhost"
SERVICE = "http://wp.svc"


def cfg(timeout=5.0):
    return Config(
        home_url=HOME,
        service_url=SERVICE,
        consumer_key="ck_" + "a" * 40,
        consumer_secret="cs_" + "b" * 40,
        timeout_seconds=timeout,
    )


def mount(handler, timeout=5.0):
    server.set_client(WooClient(cfg(timeout), transport=httpx.MockTransport(handler)))


def q(request):
    return {k: v[0] for k, v in parse_qs(urlparse(str(request.url)).query).items()}


# ---------------------------------------------------------------- products

def test_list_products_summarises():
    def h(req):
        return httpx.Response(200, json=[
            {"id": 11, "name": "Demo Widget", "sku": "DEMO-WIDGET-1",
             "price": "19.99", "status": "publish", "permalink": "http://x/p",
             "description": "ignored"},
        ])
    mount(h)
    out = server.list_products()
    assert out == [{
        "id": 11, "name": "Demo Widget", "sku": "DEMO-WIDGET-1",
        "price": "19.99", "status": "publish", "permalink": "http://x/p",
    }]


def test_list_products_rejects_bad_per_page():
    mount(lambda r: httpx.Response(200, json=[]))
    with pytest.raises(ToolError):
        server.list_products(per_page=0)
    with pytest.raises(ToolError):
        server.list_products(per_page=101)


def test_create_product_posts_expected_body():
    seen = {}

    def h(req):
        # create_product also reads the store currency so the returned
        # summary can label its price. That is a GET; only record the POST.
        if urlparse(str(req.url)).path.endswith("/settings/general"):
            return httpx.Response(200, json=[{"id": "woocommerce_currency", "value": "USD"}])
        seen["body"] = req.content.decode()
        seen["method"] = req.method
        return httpx.Response(201, json={"id": 99, "name": "New", "price": "1.50",
                                         "sku": None, "status": "publish", "permalink": "u"})
    mount(h)
    out = server.create_product(name="New", regular_price="1.50")
    assert seen["method"] == "POST"
    assert '"type": "simple"' in seen["body"]
    assert '"status": "publish"' in seen["body"]
    assert out["id"] == 99
    assert out["currency"] == "USD"


@pytest.mark.parametrize("price", ["abc", "-1", ""])
def test_create_product_rejects_bad_price(price):
    mount(lambda r: httpx.Response(200, json={}))
    with pytest.raises(ToolError):
        server.create_product(name="x", regular_price=price)


def test_create_product_rejects_blank_name():
    mount(lambda r: httpx.Response(200, json={}))
    with pytest.raises(ToolError):
        server.create_product(name="   ", regular_price="1.00")


# ---------------------------------------------------------------- orders

def test_list_orders_today_uses_store_timezone_not_utc():
    """'today' must be resolved in the store's timezone.

    The store here is Asia/Kolkata (UTC+5:30). The UTC window for that local
    day must therefore start at 18:30 the previous day, not at 00:00 UTC.

    The zone is mocked on the REST API index at /wp-json/, which is where
    WordPress actually publishes it. This test used to mock it on
    system_status's environment.default_timezone, which is PHP's process
    timezone and is always UTC on a real site, so the test agreed with the
    bug it was meant to catch. See tests/test_store_settings.py.
    """
    seen = {}

    def h(req):
        path = urlparse(str(req.url)).path
        if path == "/wp-json/":
            return httpx.Response(200, json={"timezone_string": "Asia/Kolkata",
                                             "gmt_offset": 5.5})
        seen["q"] = q(req)
        return httpx.Response(200, json=[])

    mount(h)
    server.list_orders(date="2026-10-17")
    assert seen["q"]["after"] == "2026-10-16T18:30:00"
    assert seen["q"]["before"] == "2026-10-17T18:30:00"


def test_list_orders_utc_store_uses_midnight_utc():
    def h(req):
        path = urlparse(str(req.url)).path
        if path == "/wp-json/":
            return httpx.Response(200, json={"timezone_string": "UTC", "gmt_offset": 0})
        h.q = q(req)
        return httpx.Response(200, json=[])

    mount(h)
    server.list_orders(date="2026-10-17")
    assert h.q["after"] == "2026-10-17T00:00:00"
    assert h.q["before"] == "2026-10-18T00:00:00"


def test_list_orders_rejects_bad_date():
    def h(req):
        if urlparse(str(req.url)).path == "/wp-json/":
            return httpx.Response(200, json={"timezone_string": "UTC", "gmt_offset": 0})
        return httpx.Response(200, json=[])
    mount(h)
    with pytest.raises(ToolError):
        server.list_orders(date="17-10-2026")


def test_get_order_rejects_non_positive_id():
    mount(lambda r: httpx.Response(200, json={}))
    with pytest.raises(ToolError):
        server.get_order(0)


def test_update_order_status_rejects_unknown_status():
    mount(lambda r: httpx.Response(200, json={}))
    with pytest.raises(ToolError):
        server.update_order_status(12, "shipped")


def test_update_order_status_sends_put():
    seen = {}

    def h(req):
        seen["method"] = req.method
        seen["body"] = req.content.decode()
        return httpx.Response(200, json={"id": 12, "status": "completed", "total": "19.99"})
    mount(h)
    out = server.update_order_status(12, "completed")
    assert seen["method"] == "PUT"
    assert '"status": "completed"' in seen["body"]
    assert out["status"] == "completed"


# ---------------------------------------------------------------- failures

def test_timeout_becomes_a_clear_tool_error():
    def h(req):
        raise httpx.ReadTimeout("too slow", request=req)
    mount(h, timeout=2.0)
    with pytest.raises(ToolError) as e:
        server.list_products()
    msg = str(e.value)
    assert "did not respond within 2.0s" in msg
    assert "GET /wp-json/wc/v3/products" in msg


def test_http_error_includes_store_message():
    def h(req):
        return httpx.Response(401, json={"code": "woocommerce_rest_authentication_error",
                                         "message": "Invalid signature"})
    mount(h)
    with pytest.raises(ToolError) as e:
        server.list_products()
    assert "HTTP 401" in str(e.value)
    assert "Invalid signature" in str(e.value)


def test_connection_error_is_not_a_crash():
    def h(req):
        raise httpx.ConnectError("refused", request=req)
    mount(h)
    with pytest.raises(ToolError) as e:
        server.list_products()
    assert "could not reach the store" in str(e.value)


def test_store_timezone_falls_back_to_utc_when_store_is_down():
    def h(req):
        raise httpx.ConnectError("refused", request=req)
    c = WooClient(cfg(), transport=httpx.MockTransport(h))
    assert c.store_timezone() == "UTC"


# ---------------------------------------------------------------- config

def test_config_redacted_never_leaks_credentials():
    r = cfg().redacted()
    assert r["consumer_key"] == "<redacted>"
    assert r["consumer_secret"] == "<redacted>"
    assert "ck_" not in str(r)
    assert "cs_" not in str(r)


# -------------------------------------------- WM-8 regression: error surfacing

def test_woo_error_becomes_tool_error_so_the_model_can_read_it():
    """REGRESSION, WM-8.

    The SDK only shows the model a message when a tool raises its own
    ToolError. Any other exception is a crash: the model sees the bare
    "Error executing tool <name>" and the real text is withheld. WooError
    describes anticipated failures that the caller most needs to read, so
    every tool converts it at the MCP boundary.

    Caught live: with WordPress scaled to 0 the client received only
    "Error executing tool list_products" until this conversion was added.
    """
    def h(req):
        raise httpx.ConnectError("refused", request=req)

    mount(h)
    with pytest.raises(ToolError) as e:
        server.list_products()
    assert "could not reach the store" in str(e.value)
    # and it must not be the bare crash message
    assert str(e.value) != "Error executing tool list_products"


def test_every_tool_surfaces_woo_errors():
    """All five tools, not just the one that was tested by hand."""
    def h(req):
        raise httpx.ConnectError("refused", request=req)

    mount(h)
    calls = [
        (server.list_products, (), {}),
        (server.create_product, (), {"name": "n", "regular_price": "1.00"}),
        (server.get_order, (12,), {}),
        (server.update_order_status, (12, "completed"), {}),
    ]
    for fn, a, kw in calls:
        with pytest.raises(ToolError):
            fn(*a, **kw)


# ------------------------------------ store timezone, with a frozen clock

def test_today_uses_store_timezone_at_a_boundary_instant(monkeypatch):
    """At 00:30 IST the IST date and the UTC date disagree. That is the only
    time a UTC bug is visible, so freeze the clock there.

    Instant: 2026-10-17T19:00:00Z == 2026-10-18T00:30:00+05:30.
      correct (Asia/Kolkata): today is the 18th
        -> window 2026-10-17T18:30:00Z .. 2026-10-18T18:30:00Z
      wrong (UTC):            today is the 17th
        -> window 2026-10-17T00:00:00Z .. 2026-10-18T00:00:00Z

    A store whose timezone is read but then ignored would pass the earlier
    tests and fail this one.
    """
    from datetime import datetime as real_datetime, timezone as real_tz

    frozen = real_datetime(2026, 10, 17, 19, 0, 0, tzinfo=real_tz.utc)

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen.astimezone(tz) if tz else frozen

    monkeypatch.setattr(server, "datetime", FrozenDateTime)

    seen = {}

    def h(req):
        from urllib.parse import urlparse as up
        if up(str(req.url)).path == "/wp-json/":
            return httpx.Response(200, json={"timezone_string": "Asia/Kolkata",
                                             "gmt_offset": 5.5})
        seen.update(q(req))
        return httpx.Response(200, json=[])

    mount(h)
    server.list_orders(date="today")

    assert seen["after"] == "2026-10-17T18:30:00", "today was not resolved in Asia/Kolkata"
    assert seen["before"] == "2026-10-18T18:30:00"
    # The UTC-shaped window must not appear.
    assert seen["after"] != "2026-10-17T00:00:00", "today fell back to UTC"


# ------------------------------------------- schema richness regression

def test_tool_schemas_load_and_status_carries_its_enum():
    """REGRESSION, two faults in one test.

    1. Importing the module must actually register the tools. `from __future__
       import annotations` makes annotations strings and @mcp.tool() evaluates
       them at DEFINITION time, so a type alias declared below the first tool
       that uses it raises InvalidSignature at import. `py_compile` does not
       catch that, because compiling never evaluates annotations. Only an
       import does, which is what this test performs.

    2. `status` must reach clients as an enum, not a bare string. Otherwise a
       model learns the eight valid values only by guessing and being
       rejected.
    """
    import asyncio
    tools = asyncio.run(server.mcp.list_tools())
    assert sorted(t.name for t in tools) == [
        "create_product", "get_order", "list_orders",
        "list_products", "update_order_status",
    ]
    status = [t for t in tools if t.name == "update_order_status"][0] \
        .input_schema["properties"]["status"]
    assert status.get("enum") == list(server.VALID_STATUSES)
