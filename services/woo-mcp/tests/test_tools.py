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
    """
    seen = {}

    def h(req):
        path = urlparse(str(req.url)).path
        if path.endswith("/system_status"):
            return httpx.Response(200, json={"environment": {"default_timezone": "Asia/Kolkata"}})
        seen["q"] = q(req)
        return httpx.Response(200, json=[])

    mount(h)
    server.list_orders(date="2026-10-17")
    assert seen["q"]["after"] == "2026-10-16T18:30:00"
    assert seen["q"]["before"] == "2026-10-17T18:30:00"


def test_list_orders_utc_store_uses_midnight_utc():
    def h(req):
        path = urlparse(str(req.url)).path
        if path.endswith("/system_status"):
            return httpx.Response(200, json={"environment": {"default_timezone": "UTC"}})
        h.q = q(req)
        return httpx.Response(200, json=[])

    mount(h)
    server.list_orders(date="2026-10-17")
    assert h.q["after"] == "2026-10-17T00:00:00"
    assert h.q["before"] == "2026-10-18T00:00:00"


def test_list_orders_rejects_bad_date():
    def h(req):
        if urlparse(str(req.url)).path.endswith("/system_status"):
            return httpx.Response(200, json={"environment": {"default_timezone": "UTC"}})
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
