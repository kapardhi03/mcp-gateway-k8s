"""Thin WooCommerce REST client: OAuth-signed, always timed out.

Every failure becomes a WooError with a message a model can act on. Nothing
here raises a bare transport exception at the caller, and nothing hangs: the
timeout is mandatory and comes from config.
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlencode

import httpx2 as httpx

from .config import Config
from .oauth import sign


# Store settings are read on hot paths and change about never.
SETTINGS_TTL = 300.0


class WooError(RuntimeError):
    """A WooCommerce call failed in a way the caller should surface."""


class WooClient:
    def __init__(self, config: Config, transport: Any = None) -> None:
        self._c = config
        # `transport` exists so tests can inject a mock without a network.
        self._transport = transport
        # Store settings change about never and are read on every date-bounded
        # orders call. system_status in particular is one of the heaviest
        # endpoints WooCommerce has: it enumerates plugins, theme, database
        # tables and more. Cache it.
        self._cache: dict[str, tuple[float, Any]] = {}

    def _cached(self, key: str, produce: Any, ttl: float = SETTINGS_TTL) -> Any:
        hit = self._cache.get(key)
        if hit is not None and (time.monotonic() - hit[0]) < ttl:
            return hit[1]
        value = produce()
        self._cache[key] = (time.monotonic(), value)
        return value

    # ---------- internals ----------

    def _request(
        self,
        method: str,
        path: str,
        query: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        params = sign(
            method=method,
            home_url=self._c.home_url,
            path=path,
            consumer_key=self._c.consumer_key,
            consumer_secret=self._c.consumer_secret,
            extra_params=query or {},
        )
        url = "%s%s?%s" % (self._c.service_url, path, urlencode(params))
        headers = {"Host": self._c.host_header, "Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"

        try:
            with httpx.Client(timeout=self._c.timeout_seconds, transport=self._transport) as client:
                resp = client.request(
                    method,
                    url,
                    headers=headers,
                    content=json.dumps(body).encode() if body is not None else None,
                )
        except httpx.TimeoutException as exc:
            raise WooError(
                "the store did not respond within %.1fs (%s %s). It may be down or overloaded."
                % (self._c.timeout_seconds, method, path)
            ) from exc
        except httpx.HTTPError as exc:
            raise WooError(
                "could not reach the store at %s (%s %s): %s"
                % (self._c.service_url, method, path, type(exc).__name__)
            ) from exc

        if resp.status_code >= 400:
            detail = ""
            try:
                payload = resp.json()
                detail = payload.get("message") or payload.get("code") or ""
            except Exception:
                detail = resp.text[:200]
            raise WooError(
                "the store rejected %s %s with HTTP %d%s"
                % (method, path, resp.status_code, (": " + detail) if detail else "")
            )

        try:
            return resp.json()
        except Exception as exc:
            raise WooError("the store returned a non-JSON response to %s %s" % (method, path)) from exc

    # ---------- api ----------

    def get(self, path: str, query: dict[str, str] | None = None) -> Any:
        return self._request("GET", path, query=query)

    def post(self, path: str, body: dict[str, Any]) -> Any:
        return self._request("POST", path, body=body)

    def put(self, path: str, body: dict[str, Any]) -> Any:
        return self._request("PUT", path, body=body)

    def store_currency(self) -> str:
        """The store's currency code, read from WooCommerce, not assumed.

        Product prices come back from the REST API as bare strings with no
        currency anywhere in the payload. The chat agent noticed: asked for
        the cheapest product in euros it answered correctly but had to add
        "I assumed the store currency is USD, since the tools didn't state
        it". A price without its currency is an incomplete answer, and a
        model left to guess one will eventually guess wrong.

        Orders are unaffected: an order payload carries its own currency.

        Read from /wc/v3/settings/general rather than system_status, which
        also carries it but costs far more to produce.
        """
        def produce() -> str:
            try:
                rows = self.get("/wp-json/wc/v3/settings/general")
            except WooError:
                return ""
            if not isinstance(rows, list):
                return ""
            for row in rows:
                if isinstance(row, dict) and row.get("id") == "woocommerce_currency":
                    return str(row.get("value") or "")
            return ""

        return self._cached("currency", produce)

    def store_timezone(self) -> str:
        """The store's timezone name, read from WordPress, not assumed.

        'Today' must mean today in the store's timezone, not UTC.

        Read from the REST API index at /wp-json/, which exposes
        `timezone_string` and `gmt_offset`. That endpoint needs no
        authentication and is cheap.

        NOT from system_status's `environment.default_timezone`, which is
        what this method used until 2026-10-20 and is the WRONG field: it
        reports PHP's process timezone, and WordPress forces that to UTC on
        every request while keeping the site timezone separately. So this
        returned "UTC" for a store set to Asia/Kolkata, and `_day_bounds`
        resolved "today" in UTC while the requirements trace claimed the
        store's zone.

        It hid because of which orders the difference actually touches.
        IST is UTC+5:30, so the store's "today" window and a UTC "today"
        window are always offset by 5h30m at each end, but an order only
        lands in the gap if it was placed between 00:00 and 05:30 IST. Every
        order in this project had been placed in the daytime, where both
        implementations agree, so the bug was invisible. Same shape as the
        gmt_offset Job failure: a thing that looks like it works.

        A site can be configured with a raw UTC offset and no named zone, in
        which case `timezone_string` is empty and `gmt_offset` is the only
        answer; a fixed-offset zone is built from it.
        """
        def produce() -> str:
            try:
                index = self.get("/wp-json/")
            except WooError:
                return "UTC"
            if not isinstance(index, dict):
                return "UTC"
            name = str(index.get("timezone_string") or "").strip()
            if name:
                return name
            offset = index.get("gmt_offset")
            if offset is None:
                return "UTC"
            try:
                hours = float(offset)
            except (TypeError, ValueError):
                return "UTC"
            # ZoneInfo cannot take an offset, but "UTC+05:30" style is not a
            # zone name either. Return the sign-flipped Etc/GMT form, which
            # IS a real zone: Etc/GMT-5 is UTC+5. Whole hours only, so a
            # half-hour offset with no named zone falls back to UTC rather
            # than silently rounding.
            if hours != int(hours):
                return "UTC"
            sign = "-" if hours > 0 else "+"
            return "Etc/GMT%s%d" % (sign, abs(int(hours)))

        return self._cached("timezone", produce)
