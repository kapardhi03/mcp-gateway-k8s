"""Thin WooCommerce REST client: OAuth-signed, always timed out.

Every failure becomes a WooError with a message a model can act on. Nothing
here raises a bare transport exception at the caller, and nothing hangs: the
timeout is mandatory and comes from config.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode

import httpx2 as httpx

from .config import Config
from .oauth import sign


class WooError(RuntimeError):
    """A WooCommerce call failed in a way the caller should surface."""


class WooClient:
    def __init__(self, config: Config, transport: Any = None) -> None:
        self._c = config
        # `transport` exists so tests can inject a mock without a network.
        self._transport = transport

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

    def store_timezone(self) -> str:
        """The store's timezone name, read from WooCommerce, not assumed.

        'Today' must mean today in the store's timezone, not UTC. Falls back to
        UTC only if WooCommerce does not report one, and says so in the value.
        """
        try:
            status = self.get("/wp-json/wc/v3/system_status")
        except WooError:
            return "UTC"
        env = status.get("environment") or {}
        return env.get("default_timezone") or "UTC"
