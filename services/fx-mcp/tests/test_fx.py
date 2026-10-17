"""fx-mcp tool tests. Mocked transport, never touches the network."""

from __future__ import annotations

import httpx2 as httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from fx_mcp import server

# A real Frankfurter response, captured 2026-10-17 from the dated endpoint so
# the fixture is a fact rather than an invention.
DATED = {"amount": 1.0, "base": "USD", "date": "2026-10-16", "rates": {"EUR": 0.88865}}


def mount(handler):
    server.set_transport(httpx.MockTransport(handler))


def ok(payload):
    return lambda req: httpx.Response(200, json=payload)


def test_rates_returns_base_date_and_rates():
    mount(ok(DATED))
    out = server.rates(base="USD", symbols="EUR", date="2026-10-16")
    assert out == {"base": "USD", "date": "2026-10-16", "rates": {"EUR": 0.88865}}


def test_convert_uses_the_rate_and_rounds_to_cents():
    mount(ok(DATED))
    out = server.convert(amount=19.99, from_currency="USD", to_currency="EUR", date="2026-10-16")
    assert out["rate"] == 0.88865
    # 19.99 * 0.88865 = 17.76410... -> 17.76
    assert out["converted"] == 17.76
    assert out["from"] == "USD" and out["to"] == "EUR"


def test_convert_same_currency_short_circuits_without_a_call():
    def explode(req):
        raise AssertionError("must not call the API when from == to")

    mount(explode)
    out = server.convert(amount=5, from_currency="eur", to_currency="EUR")
    assert out["rate"] == 1.0 and out["converted"] == 5.0


@pytest.mark.parametrize("code", ["US", "USDD", "US1", "", "  "])
def test_bad_currency_codes_rejected(code):
    mount(ok(DATED))
    with pytest.raises(ToolError):
        server.convert(amount=1, from_currency=code, to_currency="EUR")


def test_lowercase_codes_are_accepted_and_normalised():
    seen = {}

    def h(req):
        seen["params"] = dict(req.url.params)
        return httpx.Response(200, json=DATED)

    mount(h)
    server.rates(base="usd", symbols="eur")
    assert seen["params"]["base"] == "USD"
    assert seen["params"]["symbols"] == "EUR"


def test_bad_date_rejected():
    mount(ok(DATED))
    with pytest.raises(ToolError):
        server.rates(base="USD", date="16-10-2026")


def test_negative_amount_rejected():
    mount(ok(DATED))
    with pytest.raises(ToolError):
        server.convert(amount=-1, from_currency="USD", to_currency="EUR")


def test_missing_rate_is_a_clear_error():
    mount(ok({"base": "USD", "date": "2026-10-16", "rates": {}}))
    with pytest.raises(ToolError) as e:
        server.convert(amount=1, from_currency="USD", to_currency="EUR")
    assert "no rate available" in str(e.value)


def test_timeout_is_a_tool_error_not_a_hang():
    def h(req):
        raise httpx.ReadTimeout("slow", request=req)

    mount(h)
    with pytest.raises(ToolError) as e:
        server.rates()
    assert "did not respond within" in str(e.value)


def test_connection_error_is_a_tool_error():
    def h(req):
        raise httpx.ConnectError("refused", request=req)

    mount(h)
    with pytest.raises(ToolError) as e:
        server.rates()
    assert "could not reach the rates service" in str(e.value)


def test_http_error_surfaces_status():
    mount(lambda req: httpx.Response(503, text="upstream down"))
    with pytest.raises(ToolError) as e:
        server.rates()
    assert "HTTP 503" in str(e.value)
