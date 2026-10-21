"""The model behind the chat agent. See D-011.

One small provider interface, chosen by the Helm value `llm.provider`, so
switching away from the Anthropic API is a values change and not a code
change. Only the Anthropic provider is implemented; see `Gemini` at the
bottom for why, and for what it would take.

Nothing here logs a request body, a response body or a key. A request body
carries the user's question and a response body carries the model's answer;
neither belongs in a pod log, and the key belongs nowhere.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx2 as httpx

log = logging.getLogger("gateway.llm")

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
# Pinned. The Anthropic API versions its wire format with this header rather
# than with the URL, so leaving it out gets a 400, not a "latest".
ANTHROPIC_VERSION = "2023-06-01"


class LlmError(RuntimeError):
    """The model call failed. The message is safe to show a signed-in user."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Turn:
    """One model response."""

    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    # Carried verbatim back into the next request as the assistant message.
    # It must not be rebuilt from `text`: an adaptive-thinking model returns
    # thinking blocks here and the API rejects a follow-up that drops them.
    raw_content: list[dict[str, Any]] = field(default_factory=list)
    wants_tools: bool = False


class Anthropic:
    """Messages API, manual tool loop.

    Verified against https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview
    on 2026-10-20:
      * headers    x-api-key, anthropic-version, content-type
      * tools      [{name, description, input_schema}]
      * tool_use   {type, id, name, input}
      * tool_result {type: "tool_result", tool_use_id, content}, in a USER message
      * stop_reason "tool_use" is the signal to run a tool

    Two deliberate settings, both about cost (D-011):
      * output_config.effort = "low". Thinking is adaptive and always on, and
        thinking tokens bill at the OUTPUT rate. "medium" is the default and
        is more deliberation than "what orders came in today" needs.
      * tool_choice.disable_parallel_tool_use = true. One tool per step keeps
        the step cap meaningful: six steps is then six calls at most, not six
        rounds of unbounded fan-out.
    """

    def __init__(self, api_key: str, model: str, max_tokens: int,
                 effort: str = "low", timeout: float = 60.0) -> None:
        if not api_key:
            raise LlmError("no API key configured for the Anthropic provider")
        self._key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.effort = effort
        self.timeout = timeout

    async def complete(self, system: str, messages: list[dict[str, Any]],
                       tools: list[dict[str, Any]]) -> Turn:
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": messages,
            "output_config": {"effort": self.effort},
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = {"type": "auto", "disable_parallel_tool_use": True}

        headers = {
            "x-api-key": self._key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as hc:
                r = await hc.post(ANTHROPIC_URL, json=body, headers=headers)
        except Exception as exc:
            # Type only. A transport error's text can echo the request, and
            # the request carries the key in a header.
            raise LlmError("could not reach the model API: %s" % type(exc).__name__) from exc

        if r.status_code != 200:
            raise LlmError(_api_error(r))

        data = r.json()
        content = data.get("content") or []
        text = "".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text").strip()
        calls = [
            ToolCall(id=b["id"], name=b["name"], arguments=b.get("input") or {})
            for b in content
            if isinstance(b, dict) and b.get("type") == "tool_use"
        ]
        usage = data.get("usage") or {}
        return Turn(
            text=text,
            tool_calls=calls,
            tokens_in=int(usage.get("input_tokens") or 0),
            tokens_out=int(usage.get("output_tokens") or 0),
            raw_content=content,
            wants_tools=data.get("stop_reason") == "tool_use",
        )

    @staticmethod
    def tool_result(call_id: str, content: str, is_error: bool = False) -> dict[str, Any]:
        block: dict[str, Any] = {
            "type": "tool_result", "tool_use_id": call_id, "content": content}
        if is_error:
            block["is_error"] = True
        return block


def _api_error(r: Any) -> str:
    """A short, safe description of a non-200 from the model API.

    Billing and rate-limit failures are the ones that will actually happen
    here, and an operator needs to tell them apart from a bad request. The
    response body is parsed for the API's own message, which never contains
    the key; if it cannot be parsed, only the status code is reported.
    """
    kind = {
        400: "the gateway sent the model API a request it rejected",
        401: "the model API rejected the key",
        403: "the model API refused the key",
        429: "the model API is rate limiting us",
        529: "the model API is overloaded",
    }.get(r.status_code, "the model API returned HTTP %d" % r.status_code)
    detail = ""
    try:
        err = (r.json() or {}).get("error") or {}
        msg = str(err.get("message") or "").strip()
        if msg:
            detail = ": %s" % msg[:300]
    except Exception:
        pass
    return "%s%s" % (kind, detail)


class Gemini:
    """Placeholder for the D-011 fallback provider.

    Deliberately not implemented. Writing an adapter with no key to run it
    against would put untested code on the one path that exists for when the
    Anthropic credits run out, which is the worst possible moment to find out
    it does not work. The seam is here and the work is small: Gemini's
    generateContent takes `tools: [{functionDeclarations: [...]}]` and returns
    functionCall parts, so `complete()` is a shape translation plus the same
    usage accounting.
    """

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise LlmError(
            "llm.provider=gemini is not implemented. Only 'anthropic' works today. "
            "See D-011 and the note in gateway/llm.py.")


PROVIDERS = {"anthropic": Anthropic, "gemini": Gemini}


def build(provider: str, api_key: str, model: str, max_tokens: int,
          effort: str = "low") -> Any:
    cls = PROVIDERS.get(provider)
    if cls is None:
        raise LlmError("unknown llm provider %r, expected one of %s"
                       % (provider, ", ".join(sorted(PROVIDERS))))
    return cls(api_key=api_key, model=model, max_tokens=max_tokens, effort=effort)
