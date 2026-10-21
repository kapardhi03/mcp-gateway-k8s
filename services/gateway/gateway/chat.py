"""The chat agent. D-011, C-01 to C-04.

The shape that matters, and the reason for it:

    browser  --POST /chat-->  gateway  --MCP over HTTP-->  gateway /mcp  -->  upstreams
                                 |
                                 +--HTTPS--> the model API

The agent runs server side. The browser sends a sentence and gets back an
answer plus the list of tools that were called. It never sees the model API
key, never sees an upstream URL, and never calls a tool itself.

The agent reaches its tools through the gateway's OWN public /mcp endpoint,
over HTTP on loopback, authenticating with a short-lived API key minted for
the signed-in user. That is a deliberate choice and not a detour:

  * The agent is then just another MCP client, the same as Claude Code. It
    gets the same tool list, the same `tool__name` prefixes, the same
    timeouts and the same failures. There is no second, privileged path that
    could behave differently from the one the demo shows.
  * Every tool call is authenticated as the real user by the normal
    middleware, so the audit row says "a@example.com" because that is who
    actually made the call, not because the agent asserted it.
  * Disabling an upstream removes its tools from the agent for free, because
    the agent asks the same registry everyone else asks.

The key is minted per turn and deleted when the turn ends, with an expiry as
the backstop if the process dies in between.

Credit guards, all Helm values (D-011: there is no budget to top up):
  * a step cap, so a loop cannot run away
  * a max_tokens cap per model call
  * a global per-day turn cap
  * a question length cap, because input is billed and a pasted document is
    the cheapest way to spend a lot by accident
  * a tool-result length cap, for the same reason from the other direction
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx2 as httpx
from mcp.client import ClientSession
from mcp.client.streamable_http import streamable_http_client

from . import apikeys, llm

log = logging.getLogger("gateway.chat")

SESSION_KEY_NAME = "chat-session"
SESSION_KEY_TTL = timedelta(minutes=5)

SYSTEM_PROMPT = """You are the assistant for an online store, inside a team MCP gateway.

Answer from the tools, never from memory or guesswork. If the tools cannot \
answer the question, say so plainly.

Tool names are prefixed with the server they come from, like `woo__list_orders`. \
Call one tool at a time.

When the question is about "today", pass date="today" to the orders tool. It \
resolves the day in the store's own timezone, which is not UTC. Never work out a \
date yourself.

Prices and totals come back as strings in the store's currency. If the user asks \
for another currency, convert with the fx tools rather than estimating a rate.

Keep answers short: a sentence or two, and a small list where a list is the \
answer. State figures exactly as the tools returned them."""


class ChatError(RuntimeError):
    """Safe to show a signed-in user. `status` is the HTTP status to return."""

    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class ChatConfig:
    provider: str
    model: str
    api_key: str
    effort: str
    max_steps: int
    max_tokens: int
    daily_cap: int
    max_question_chars: int
    max_tool_result_chars: int
    self_mcp_url: str
    tool_timeout_seconds: float

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


class Agent:
    def __init__(self, gw: Any, cfg: ChatConfig) -> None:
        self.gw = gw
        self.cfg = cfg

    # ---------------------------------------------------------------- keys

    async def _mint_key(self, user: Any) -> tuple[str, int]:
        full, prefix, h = apikeys.generate()
        kid = await self.gw.db.create_user_key(
            user.id, SESSION_KEY_NAME, prefix, h, user.role,
            expires_at=datetime.now(timezone.utc) + SESSION_KEY_TTL)
        return full, kid

    # ---------------------------------------------------------------- run

    async def run(self, user: Any, question: str) -> dict[str, Any]:
        cfg = self.cfg
        if not cfg.configured:
            raise ChatError(503, "the chat agent has no model API key configured")

        question = (question or "").strip()
        if not question:
            raise ChatError(400, "ask a question")
        if len(question) > cfg.max_question_chars:
            raise ChatError(
                400, "that question is %d characters; the limit is %d. Input is billed "
                     "per token, so long pastes are capped." % (len(question), cfg.max_question_chars))

        used = await self.gw.db.chat_turns_today()
        if used >= cfg.daily_cap:
            raise ChatError(
                429, "the daily chat limit of %d turns is used up (%d so far today). "
                     "It resets at midnight." % (cfg.daily_cap, used))

        provider = llm.build(cfg.provider, cfg.api_key, cfg.model, cfg.max_tokens, cfg.effort)

        started = time.monotonic()
        tokens_in = tokens_out = 0
        steps: list[dict[str, Any]] = []
        outcome, detail = "error", None
        api_key, key_id = await self._mint_key(user)
        try:
            answer, tokens_in, tokens_out, steps = await self._loop(
                provider, api_key, question)
            outcome = "ok"
            return {
                "answer": answer,
                "steps": steps,
                "tokens": {"in": tokens_in, "out": tokens_out},
                "model": cfg.model,
                "used_today": used + 1,
                "daily_cap": cfg.daily_cap,
            }
        except ChatError as exc:
            detail = exc.message
            raise
        except llm.LlmError as exc:
            detail = str(exc)
            raise ChatError(502, str(exc)) from exc
        except Exception as exc:
            detail = type(exc).__name__
            log.exception("chat turn failed")
            raise ChatError(500, "the chat agent failed: %s" % type(exc).__name__) from exc
        finally:
            # The key dies with the turn, whatever happened.
            try:
                await self.gw.db.delete_key_by_id(key_id)
            except Exception:
                log.exception("could not delete the per-turn chat key")
            ms = int((time.monotonic() - started) * 1000)
            try:
                # One row per turn, carrying its token cost. The individual
                # tool calls audit themselves through the normal middleware,
                # attributed to this same user.
                await self.gw.db.audit(
                    user.email, "chat", "turn", ms, outcome, detail,
                    tokens_in=tokens_in or None, tokens_out=tokens_out or None)
            except Exception:
                log.exception("chat audit write failed")

    # ---------------------------------------------------------------- loop

    async def _loop(self, provider: Any, api_key: str,
                    question: str) -> tuple[str, int, int, list[dict[str, Any]]]:
        cfg = self.cfg
        messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
        steps: list[dict[str, Any]] = []
        tokens_in = tokens_out = 0

        headers = {"Authorization": "Bearer %s" % api_key}
        async with httpx.AsyncClient(headers=headers, timeout=cfg.tool_timeout_seconds) as hc:
            async with streamable_http_client(cfg.self_mcp_url, http_client=hc) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    tools = _tool_schemas((await session.list_tools()).tools)

                    for _step in range(cfg.max_steps):
                        turn = await provider.complete(SYSTEM_PROMPT, messages, tools)
                        tokens_in += turn.tokens_in
                        tokens_out += turn.tokens_out

                        if not turn.wants_tools or not turn.tool_calls:
                            return (turn.text or "(the model returned no text)",
                                    tokens_in, tokens_out, steps)

                        messages.append({"role": "assistant", "content": turn.raw_content})
                        results = []
                        for call in turn.tool_calls:
                            text, is_error, ms = await self._call(session, call)
                            steps.append({
                                "tool": call.name,
                                "input": call.arguments,
                                "duration_ms": ms,
                                "outcome": "error" if is_error else "ok",
                            })
                            results.append(provider.tool_result(call.id, text, is_error))
                        messages.append({"role": "user", "content": results})

                    # Out of steps. Say so rather than returning a confident
                    # half answer built from an unfinished tool sequence.
                    raise ChatError(
                        400, "the agent reached its limit of %d tool steps without "
                             "finishing. Try a narrower question." % cfg.max_steps)

    async def _call(self, session: Any, call: llm.ToolCall) -> tuple[str, bool, int]:
        """Run one tool through the gateway. Never raises."""
        started = time.monotonic()
        try:
            result = await session.call_tool(call.name, call.arguments)
            text = _result_text(result)[: self.cfg.max_tool_result_chars]
            is_error = bool(getattr(result, "is_error", False) or getattr(result, "isError", False))
        except Exception as exc:
            # The model is told the tool failed and can try another one. The
            # text is the exception TYPE, for the same reason upstreams.py
            # gives: a transport error's message can quote request headers.
            text, is_error = "the tool call failed: %s" % type(exc).__name__, True
        return text, is_error, int((time.monotonic() - started) * 1000)


def _tool_schemas(tools: list[Any]) -> list[dict[str, Any]]:
    """MCP tool definitions to Anthropic tool definitions.

    Both use JSON Schema for arguments, so the schema passes through
    untouched. Rewriting it here would be a second place for the lossy
    round trip that already cost a day on woo-mcp's enums.
    """
    out = []
    for t in tools:
        schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", None)
        out.append({
            "name": t.name,
            "description": (getattr(t, "description", "") or t.name)[:1000],
            "input_schema": schema or {"type": "object", "properties": {}},
        })
    return out


def _result_text(result: Any) -> str:
    """The upstream's content as text, which is what the model wants."""
    parts = []
    for c in getattr(result, "content", []) or []:
        text = getattr(c, "text", None)
        if text is not None:
            parts.append(text)
    if parts:
        return "\n".join(parts)
    sc = getattr(result, "structured_content", None)
    if sc is not None:
        return json.dumps(sc)
    return "(the tool returned nothing)"
