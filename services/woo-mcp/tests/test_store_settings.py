"""Regression tests for the store timezone and currency.

The timezone bug these lock down, in full, because it is the second one of
exactly this shape in this project:

`store_timezone()` read `environment.default_timezone` from WooCommerce's
system_status. That field is PHP's PROCESS timezone, and WordPress forces it
to UTC on every request while keeping the site timezone in a separate option.
So a store set to Asia/Kolkata reported "UTC", and `_day_bounds` resolved
"today" in UTC while docs/requirements-trace.md claimed the store's own zone.

It survived because of which orders the difference touches. IST is UTC+5:30,
so the two "today" windows are always offset by 5h30m at each end, but an
order only falls in the gap if it was placed between 00:00 and 05:30 IST.
Every order in this project had been placed in the daytime, where the two
implementations agree exactly. Note the direction, which is easy to get
backwards: an evening order does NOT distinguish them.

The right source is the REST API index at /wp-json/, which exposes
`timezone_string` and `gmt_offset`, needs no authentication, and is far
cheaper than system_status.

Each test below fails if the fix is reverted. That is the point of them.
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx2 as httpx
import pytest

from woo_mcp import server
from woo_mcp.config import Config
from woo_mcp.woo import WooClient

HOME = "http://store.localhost"
SERVICE = "http://wp.svc"


def cfg():
    return Config(
        home_url=HOME, service_url=SERVICE,
        consumer_key="ck_" + "a" * 40, consumer_secret="cs_" + "b" * 40,
        timeout_seconds=5.0,
    )


def client(handler):
    return WooClient(cfg(), transport=httpx.MockTransport(handler))


def _json(payload):
    return httpx.Response(200, json=payload)


def wp_index(timezone_string="Asia/Kolkata", gmt_offset=5.5):
    """A realistic /wp-json/ payload.

    The key names and the surrounding fields are copied from what the live
    store actually returns, not invented, so a test cannot pass against a
    shape WordPress does not produce. That is the mistake the old tests made:
    they mocked system_status returning `default_timezone: "Asia/Kolkata"`,
    which no WordPress ever sends, and so they agreed with the bug.
    """
    return {
        "name": "Demo Store",
        "description": "",
        "url": "http://store.localhost",
        "home": "http://store.localhost",
        "gmt_offset": gmt_offset,
        "timezone_string": timezone_string,
        "namespaces": ["wp/v2", "wc/v3"],
        "authentication": {},
        "routes": {},
        "site_icon": 0,
        "site_icon_url": "",
        "site_logo": 0,
        "page_on_front": 0,
        "page_for_posts": 0,
        "show_on_front": "posts",
        "_links": {},
    }


def store(index=None, general=None, system_status=None, seen=None):
    """A mock store. `seen` collects the paths actually requested."""

    def handler(request):
        path = urlparse(str(request.url)).path
        if seen is not None:
            seen.append(path)
        if path == "/wp-json/":
            return _json(index if index is not None else {})
        if path == "/wp-json/wc/v3/settings/general":
            return _json(general if general is not None else [])
        if path == "/wp-json/wc/v3/system_status":
            return _json(system_status if system_status is not None else {})
        if path == "/wp-json/wc/v3/products":
            return _json([{"id": 1, "name": "Widget", "sku": "W-1",
                           "price": "4.50", "status": "publish",
                           "permalink": HOME + "/?p=1"}])
        return httpx.Response(404, json={"message": "no route " + path})

    return handler


# ------------------------------------------------------- timezone, the bug

def test_timezone_comes_from_the_rest_index():
    c = client(store(index=wp_index()))
    assert c.store_timezone() == "Asia/Kolkata"


def test_system_status_default_timezone_is_ignored():
    """The regression itself.

    The store is Asia/Kolkata. system_status reports PHP's process timezone,
    UTC, exactly as a real WordPress does. Reading that field instead of the
    index is the bug, so this test fails the moment anyone goes back to it.
    """
    seen: list[str] = []
    c = client(store(
        index=wp_index(),
        system_status={"environment": {"default_timezone": "UTC"},
                       "settings": {"currency": "USD"}},
        seen=seen,
    ))
    assert c.store_timezone() == "Asia/Kolkata"
    # And it did not pay for system_status to find out.
    assert "/wp-json/wc/v3/system_status" not in seen


def test_timezone_falls_back_to_gmt_offset_when_unnamed():
    """A site can be set to a raw UTC offset with no named zone."""
    c = client(store(index=wp_index(timezone_string="", gmt_offset=5)))
    # Etc/GMT-5 is UTC+5. The sign is inverted in the Etc zone names, which
    # is why this is asserted rather than assumed.
    assert c.store_timezone() == "Etc/GMT-5"
    offset = datetime(2026, 10, 20, tzinfo=ZoneInfo("Etc/GMT-5")).utcoffset()
    assert offset.total_seconds() == 5 * 3600


def test_timezone_half_hour_offset_without_a_name_does_not_round():
    """5.5 has no Etc zone. Rounding it to 5 or 6 would be a silent lie."""
    c = client(store(index=wp_index(timezone_string="", gmt_offset=5.5)))
    assert c.store_timezone() == "UTC"


def test_timezone_falls_back_to_utc_when_the_store_is_unreachable():
    def dead(_request):
        raise httpx.ConnectError("down")

    assert client(dead).store_timezone() == "UTC"


# ------------------------------------------- the bounds the timezone feeds

def test_day_bounds_shift_by_the_store_offset():
    """An explicit date in Asia/Kolkata starts at 18:30 UTC the day before.

    This is what the bug cost: with "UTC" the window was 00:00 to 00:00 UTC,
    so for five and a half hours every day it covered the wrong orders.
    """
    after, before = server._day_bounds("Asia/Kolkata", "2026-10-20")
    assert after == "2026-10-19T18:30:00"
    assert before == "2026-10-20T18:30:00"

    after_utc, before_utc = server._day_bounds("UTC", "2026-10-20")
    assert after_utc == "2026-10-20T00:00:00"
    assert (after, before) != (after_utc, before_utc)


def test_today_windows_differ_by_the_offset_at_both_ends(monkeypatch):
    """The two windows are never the same, whatever the time of day."""
    # 2026-10-20 17:30 UTC is 2026-10-20 23:00 IST.
    fixed = datetime(2026, 10, 20, 17, 30, tzinfo=ZoneInfo("UTC"))

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz is not None else fixed

    monkeypatch.setattr(server, "datetime", Frozen)

    ist_after, ist_before = server._day_bounds("Asia/Kolkata", "today")
    utc_after, utc_before = server._day_bounds("UTC", "today")

    # The store's day began at 18:30 UTC on the 19th and has not ended.
    assert (ist_after, ist_before) == ("2026-10-19T18:30:00", "2026-10-20T18:30:00")
    assert (utc_after, utc_before) == ("2026-10-20T00:00:00", "2026-10-21T00:00:00")


def test_an_order_just_after_ist_midnight_is_today_only_for_the_store(monkeypatch):
    """The one case that tells the fixed code from the bug.

    An order placed at 02:51 IST is 21:21 UTC the PREVIOUS day. The store's
    "today" includes it; a UTC "today" calls it yesterday and leaves it out.
    An order placed in the evening IST is inside both windows, so it proves
    nothing: that is the direction this project got backwards once, and it is
    why DOD-04 has to use an order from the small hours IST.
    """
    placed = "2026-10-21T21:21:00"      # 2026-10-22 02:51 IST

    # Asked later the same IST day, which is the ordinary demo case.
    fixed = datetime(2026, 10, 22, 8, 30, tzinfo=ZoneInfo("UTC"))   # 14:00 IST

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz is not None else fixed

    monkeypatch.setattr(server, "datetime", Frozen)

    ist_after, ist_before = server._day_bounds("Asia/Kolkata", "today")
    utc_after, utc_before = server._day_bounds("UTC", "today")

    assert ist_after <= placed < ist_before, "the store should count this order as today"
    assert not (utc_after <= placed < utc_before), "a UTC store would call it yesterday"

    # And the counter-case: an evening order is in both, so it is useless as
    # evidence either way.
    evening = "2026-10-22T13:30:00"     # 19:00 IST
    assert ist_after <= evening < ist_before
    assert utc_after <= evening < utc_before


def test_frozen_at_0030_ist_the_two_implementations_disagree(monkeypatch):
    """00:30 IST, the first half hour of the store's day.

    This is the sharpest point in the cycle. IST has rolled into 22 October
    while UTC is still on the 21st, so the store and a UTC implementation do
    not even agree on which DATE "today" is, let alone which window:

        store, Asia/Kolkata : 21 Oct 18:30 UTC .. 22 Oct 18:30 UTC   (22 Oct IST)
        buggy, UTC          : 21 Oct 00:00 UTC .. 22 Oct 00:00 UTC   (21 Oct UTC)

    DOD-04 is being run as the plain version, with an order placed and the
    agent returning it, which proves the requirement but not this edge
    because an order placed in daylight sits inside both windows. This test
    is what covers the edge instead.
    """
    # 2026-10-21 19:00 UTC is 2026-10-22 00:30 IST.
    fixed = datetime(2026, 10, 21, 19, 0, tzinfo=ZoneInfo("UTC"))

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz is not None else fixed

    monkeypatch.setattr(server, "datetime", Frozen)

    assert Frozen.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M") == "2026-10-22 00:30"
    assert Frozen.now(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M") == "2026-10-21 19:00"

    assert server._day_bounds("Asia/Kolkata", "today") == (
        "2026-10-21T18:30:00", "2026-10-22T18:30:00")
    assert server._day_bounds("UTC", "today") == (
        "2026-10-21T00:00:00", "2026-10-22T00:00:00")

    # An order placed right now, at 00:30 IST, asked about later the same IST
    # day once UTC has rolled over, is the case that separates them.
    placed = "2026-10-21T19:00:00"
    later = datetime(2026, 10, 22, 9, 0, tzinfo=ZoneInfo("UTC"))      # 14:30 IST

    class FrozenLater(datetime):
        @classmethod
        def now(cls, tz=None):
            return later.astimezone(tz) if tz is not None else later

    monkeypatch.setattr(server, "datetime", FrozenLater)
    i0, i1 = server._day_bounds("Asia/Kolkata", "today")
    u0, u1 = server._day_bounds("UTC", "today")
    assert i0 <= placed < i1, "the store must still count it as today"
    assert not (u0 <= placed < u1), "a UTC store drops it once UTC rolls over"


# ------------------------------------------------------------- currency

def test_currency_comes_from_settings_general():
    c = client(store(general=[
        {"id": "woocommerce_store_address", "value": "somewhere"},
        {"id": "woocommerce_currency", "value": "USD"},
    ]))
    assert c.store_currency() == "USD"


def test_currency_is_empty_rather_than_guessed_when_absent():
    """No currency is better than a wrong one. The field is then omitted."""
    c = client(store(general=[{"id": "woocommerce_store_address", "value": "x"}]))
    assert c.store_currency() == ""
    assert "currency" not in server._product_summary({"id": 1}, "")


def test_product_summary_carries_the_currency():
    assert server._product_summary({"id": 1, "price": "4.50"}, "USD")["currency"] == "USD"


def test_list_products_labels_prices_with_the_currency():
    server.set_client(client(store(
        index=wp_index(),
        general=[{"id": "woocommerce_currency", "value": "USD"}],
    )))
    rows = server.list_products()
    assert rows[0]["price"] == "4.50"
    assert rows[0]["currency"] == "USD"


# -------------------------------------------------------------- caching

def test_store_settings_are_cached():
    """These are read on every date-bounded orders call.

    system_status was the old source and is one of the heaviest endpoints
    WooCommerce has. Even against the cheap index, re-reading it per call is
    a request the store does not need to serve.
    """
    seen: list[str] = []
    c = client(store(index=wp_index(),
                     general=[{"id": "woocommerce_currency", "value": "USD"}],
                     seen=seen))
    for _ in range(5):
        assert c.store_timezone() == "Asia/Kolkata"
        assert c.store_currency() == "USD"
    assert seen.count("/wp-json/") == 1
    assert seen.count("/wp-json/wc/v3/settings/general") == 1
