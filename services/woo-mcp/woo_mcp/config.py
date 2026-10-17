"""Configuration for woo-mcp. Everything comes from the environment.

Credentials arrive from a Kubernetes Secret as env vars. Nothing is read from
a file and nothing is logged. See D-019.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    pass


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError("missing required environment variable: %s" % name)
    return value


@dataclass(frozen=True)
class Config:
    # The store's configured home URL. This is what gets SIGNED, because
    # WooCommerce builds its OAuth base string from get_home_url(). See D-006.
    home_url: str
    # The address woo-mcp actually connects to, normally a ClusterIP Service.
    # This is never signed.
    service_url: str
    consumer_key: str
    consumer_secret: str
    timeout_seconds: float

    @property
    def host_header(self) -> str:
        """Host header to send, taken from home_url.

        Without this WordPress sees a mismatched Host and issues a canonical
        redirect to the home URL, which breaks the request.
        """
        from urllib.parse import urlparse

        return urlparse(self.home_url).netloc

    @classmethod
    def from_env(cls) -> "Config":
        timeout_raw = os.environ.get("WOO_TIMEOUT_SECONDS", "10").strip()
        try:
            timeout = float(timeout_raw)
        except ValueError as exc:
            raise ConfigError("WOO_TIMEOUT_SECONDS is not a number: %r" % timeout_raw) from exc
        if timeout <= 0:
            raise ConfigError("WOO_TIMEOUT_SECONDS must be positive, got %r" % timeout_raw)

        return cls(
            home_url=_required("STORE_HOME_URL").rstrip("/"),
            service_url=_required("STORE_SERVICE_URL").rstrip("/"),
            consumer_key=_required("WOO_CONSUMER_KEY"),
            consumer_secret=_required("WOO_CONSUMER_SECRET"),
            timeout_seconds=timeout,
        )

    def redacted(self) -> dict[str, str]:
        """Safe to log. Never includes the key or the secret."""
        return {
            "home_url": self.home_url,
            "service_url": self.service_url,
            "consumer_key": "<redacted>",
            "consumer_secret": "<redacted>",
            "timeout_seconds": str(self.timeout_seconds),
        }
