"""OAuth 1.0a signing tests, including the regression test for the D-006 trap."""

from __future__ import annotations

import base64
import hashlib
import hmac
from urllib.parse import parse_qs, urlparse

import httpx2 as httpx
import pytest

from woo_mcp.config import Config
from woo_mcp.oauth import sign, signature_base_string
from woo_mcp.woo import WooClient

HOME = "http://store.localhost"
SERVICE = "http://store-store-wp.store.svc.cluster.local"
PATH = "/wp-json/wc/v3/products"
CK = "ck_" + "a" * 40
CS = "cs_" + "b" * 40


def _cfg(**kw):
    base = dict(
        home_url=HOME,
        service_url=SERVICE,
        consumer_key=CK,
        consumer_secret=CS,
        timeout_seconds=5.0,
    )
    base.update(kw)
    return Config(**base)


def _expected_signature(home_url: str, params: dict[str, str]) -> str:
    """Recompute a signature the way WooCommerce would, for a given base URL."""
    p = {k: v for k, v in params.items() if k != "oauth_signature"}
    base = signature_base_string("GET", home_url, PATH, p)
    return base64.b64encode(
        hmac.new((CS + "&").encode(), base.encode(), hashlib.sha256).digest()
    ).decode()


# ---------------------------------------------------------------- unit

def test_signing_key_has_trailing_ampersand():
    """WooCommerce does `$secret = $user->consumer_secret . '&'`.

    One-legged OAuth has no token secret, but the separator is still required.
    Dropping it produces a signature that never verifies.
    """
    params = sign("GET", HOME, PATH, CK, CS)
    without = base64.b64encode(
        hmac.new(
            CS.encode(),  # no trailing '&'
            signature_base_string(
                "GET", HOME, PATH, {k: v for k, v in params.items() if k != "oauth_signature"}
            ).encode(),
            hashlib.sha256,
        ).digest()
    ).decode()
    assert params["oauth_signature"] != without


def test_base_string_differs_between_home_and_service_url():
    """If these were equal the regression test below could not detect anything."""
    p = {"oauth_consumer_key": CK, "oauth_timestamp": "1", "oauth_nonce": "n"}
    assert signature_base_string("GET", HOME, PATH, p) != signature_base_string(
        "GET", SERVICE, PATH, p
    )


# ------------------------------------------------- the trap, end to end

def test_woo_client_signs_home_url_not_connect_url():
    """REGRESSION, D-006. The whole point of having two URLs.

    WooCommerce builds its signature base string from get_home_url(), so the
    signature must be computed over `home_url` even though the request is
    dialled at `service_url`. Signing the connect URL yields a 401 that looks
    exactly like a bad credential, so this would be easy to reintroduce and
    hard to diagnose. This test fails the moment that happens.
    """
    seen: dict[str, object] = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["host"] = request.headers.get("Host")
        return httpx.Response(200, json=[])

    WooClient(_cfg(), transport=httpx.MockTransport(handler)).get(PATH)

    url = urlparse(str(seen["url"]))
    params = {k: v[0] for k, v in parse_qs(url.query).items()}

    # It really did dial the Service.
    assert url.netloc == urlparse(SERVICE).netloc
    # And it sent the home host so WordPress does not canonical-redirect.
    assert seen["host"] == urlparse(HOME).netloc

    got = params["oauth_signature"]
    assert got == _expected_signature(HOME, params), "signature is not over home_url"
    assert got != _expected_signature(SERVICE, params), "signature was computed over service_url"


def test_host_header_comes_from_home_url():
    assert _cfg().host_header == "store.localhost"
    assert _cfg(home_url="http://store.34.93.101.10.sslip.io").host_header == (
        "store.34.93.101.10.sslip.io"
    )
