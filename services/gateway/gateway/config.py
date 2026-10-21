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
    # Chat agent. D-011. The API key is OPTIONAL on purpose: a gateway with
    # no model key must still start, serve /mcp and serve the dashboard, with
    # the Chat tab saying it is not configured. Making it required would mean
    # a reviewer with no Anthropic account could not run the project at all.
    llm_provider: str
    llm_model: str
    llm_api_key: str
    llm_effort: str
    chat_max_steps: int
    chat_max_tokens: int
    chat_daily_cap: int
    chat_max_question_chars: int
    chat_max_tool_result_chars: int

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
            llm_provider=os.environ.get("LLM_PROVIDER", "anthropic").strip(),
            llm_model=os.environ.get("LLM_MODEL", "claude-haiku-5-5").strip(),
            llm_api_key=os.environ.get("LLM_API_KEY", "").strip(),
            llm_effort=os.environ.get("LLM_EFFORT", "low").strip(),
            chat_max_steps=int(num("CHAT_MAX_STEPS", "6")),
            chat_max_tokens=int(num("CHAT_MAX_TOKENS", "1024")),
            chat_daily_cap=int(num("CHAT_DAILY_CAP", "200")),
            chat_max_question_chars=int(num("CHAT_MAX_QUESTION_CHARS", "2000")),
            chat_max_tool_result_chars=int(num("CHAT_MAX_TOOL_RESULT_CHARS", "6000")),
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
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            # Presence only. The value never reaches a log line.
            "llm_api_key": "<set>" if self.llm_api_key else "<unset>",
            "llm_effort": self.llm_effort,
            "chat_max_steps": str(self.chat_max_steps),
            "chat_max_tokens": str(self.chat_max_tokens),
            "chat_daily_cap": str(self.chat_daily_cap),
        }
