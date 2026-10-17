"""Gateway configuration. Everything from the environment, nothing from disk."""

from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    pass


def _req(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        raise ConfigError("missing required environment variable: %s" % name)
    return v


@dataclass(frozen=True)
class Config:
    database_url: str
    # Fernet key for encrypting upstream credentials at rest. From a Secret.
    encryption_key: str
    # Bootstrap admin API key, phase 1 only. From a Secret. Stored hashed on
    # first start; the plaintext is never written anywhere.
    bootstrap_api_key: str
    upstream_timeout_seconds: float
    health_interval_seconds: float

    @classmethod
    def from_env(cls) -> "Config":
        def num(name: str, default: str) -> float:
            raw = os.environ.get(name, default).strip()
            try:
                v = float(raw)
            except ValueError as exc:
                raise ConfigError("%s is not a number: %r" % (name, raw)) from exc
            if v <= 0:
                raise ConfigError("%s must be positive, got %r" % (name, raw))
            return v

        return cls(
            database_url=_req("DATABASE_URL"),
            encryption_key=_req("ENCRYPTION_KEY"),
            bootstrap_api_key=_req("BOOTSTRAP_API_KEY"),
            upstream_timeout_seconds=num("UPSTREAM_TIMEOUT_SECONDS", "8"),
            health_interval_seconds=num("HEALTH_INTERVAL_SECONDS", "30"),
        )

    def redacted(self) -> dict[str, str]:
        """Safe to log. Credentials and the DSN password never appear."""
        dsn = self.database_url
        if "@" in dsn:
            dsn = dsn.split("@", 1)[0].rsplit(":", 1)[0] + ":<redacted>@" + dsn.split("@", 1)[1]
        return {
            "database_url": dsn,
            "encryption_key": "<redacted>",
            "bootstrap_api_key": "<redacted>",
            "upstream_timeout_seconds": str(self.upstream_timeout_seconds),
            "health_interval_seconds": str(self.health_interval_seconds),
        }
