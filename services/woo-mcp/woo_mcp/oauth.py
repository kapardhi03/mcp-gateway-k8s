"""One-legged OAuth 1.0a signing for the WooCommerce REST API.

This mirrors WooCommerce's own verifier, read from the plugin source at
`includes/class-wc-rest-authentication.php` in 11.2.1. See D-006.

The part that matters, and the reason this module exists at all:

    $base_request_uri = rawurlencode( get_home_url( null, $request_path, ... ) );

WooCommerce builds the signature base string from `get_home_url()`, NOT from
the Host header and NOT from the address the client dialled. Inside the
cluster woo-mcp connects to a ClusterIP Service but must sign the store's
public home URL. Two different URLs in one request.

Signing the connect URL produces a 401 that reads exactly like a bad
credential, which is why `tests/test_oauth.py` has a regression test pinning
this behaviour.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from urllib.parse import quote

SIGNATURE_METHOD = "HMAC-SHA256"


def _rfc3986(value: object) -> str:
    """PHP rawurlencode. Unreserved set is A-Za-z0-9 and -_.~ only."""
    return quote(str(value), safe="~")


def signature_base_string(
    method: str,
    home_url: str,
    path: str,
    params: dict[str, str],
) -> str:
    """Build the string WooCommerce will HMAC.

    `home_url` is the store's configured home URL, never the connect address.

    WooCommerce sorts on the raw keys with uksort(strcmp), then percent-encodes
    keys and values, joins each pair with '=', percent-encodes the whole pair
    again, and joins the pairs with '%26'. That is equivalent to encoding the
    normalised query string once more, which is what this does.
    """
    normalised = "&".join(
        "%s=%s" % (_rfc3986(k), _rfc3986(params[k])) for k in sorted(params)
    )
    return "%s&%s&%s" % (
        method.upper(),
        _rfc3986(home_url.rstrip("/") + path),
        _rfc3986(normalised),
    )


def sign(
    method: str,
    home_url: str,
    path: str,
    consumer_key: str,
    consumer_secret: str,
    extra_params: dict[str, str] | None = None,
) -> dict[str, str]:
    """Return the full query parameters including oauth_signature."""
    params: dict[str, str] = dict(extra_params or {})
    params.update(
        {
            "oauth_consumer_key": consumer_key,
            "oauth_nonce": secrets.token_hex(16),
            "oauth_signature_method": SIGNATURE_METHOD,
            "oauth_timestamp": str(int(time.time())),
        }
    )

    base = signature_base_string(method, home_url, path, params)

    # One-legged: there is no token secret, but the '&' separator is still
    # required. WooCommerce does `$secret = $user->consumer_secret . '&'`.
    signing_key = (consumer_secret + "&").encode()

    digest = hmac.new(signing_key, base.encode(), hashlib.sha256).digest()
    params["oauth_signature"] = base64.b64encode(digest).decode()
    return params
