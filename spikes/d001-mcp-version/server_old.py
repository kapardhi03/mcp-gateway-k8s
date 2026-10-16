"""D-001 follow-up: an upstream that only speaks the old protocol.

Runs on mcp==1.28.1, whose LATEST_PROTOCOL_VERSION is 2025-11-25. Used to
answer a question the first spike did not: the gateway is an MCP *client*
to every upstream, so does the modern 2.3.0 client fall back when the
upstream cannot speak 2026-07-28?

Bound to 127.0.0.1:8766/mcp. Logs to requests_old.jsonl.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from mcp.server.fastmcp import FastMCP

HERE = Path(__file__).resolve().parent
LOG_PATH = HERE / "requests_old.jsonl"

HOST = "127.0.0.1"
PORT = 8766

mcp = FastMCP("d001-spike-old")


@mcp.tool()
def echo(text: str) -> str:
    """Return the text it was given."""
    return text


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def logging_middleware(app):
    async def wrapped(scope, receive, send):
        if scope["type"] != "http":
            await app(scope, receive, send)
            return

        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        chunks: list[bytes] = []
        more = True
        while more:
            msg = await receive()
            if msg["type"] == "http.request":
                chunks.append(msg.get("body", b""))
                more = msg.get("more_body", False)
            else:
                more = False
        body = b"".join(chunks)

        rec: dict[str, Any] = {
            "ts": _utcnow(),
            "http_method": scope.get("method"),
            "mcp_protocol_version": headers.get("mcp-protocol-version"),
            "mcp_session_id": headers.get("mcp-session-id"),
            "mcp_method": headers.get("mcp-method"),
            "user_agent": headers.get("user-agent"),
        }
        if body:
            try:
                parsed = json.loads(body)
                msgs = parsed if isinstance(parsed, list) else [parsed]
                rec["jsonrpc_methods"] = [m.get("method") for m in msgs
                                          if isinstance(m, dict) and m.get("method")]
                for m in msgs:
                    if isinstance(m, dict) and isinstance(m.get("params"), dict):
                        if m["params"].get("protocolVersion"):
                            rec["params_protocolVersion"] = m["params"]["protocolVersion"]
            except Exception:
                rec["body_prefix"] = body[:160].decode("utf-8", "replace")

        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        print(f"[old] {rec['http_method']} proto={rec['mcp_protocol_version']} "
              f"rpc={rec.get('jsonrpc_methods')}", file=sys.stderr, flush=True)

        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await app(scope, replay, send)

    return wrapped


if __name__ == "__main__":
    import mcp.types as t

    print(f"[old] mcp LATEST_PROTOCOL_VERSION = {t.LATEST_PROTOCOL_VERSION}",
          file=sys.stderr, flush=True)
    print(f"[old] listening on http://{HOST}:{PORT}/mcp", file=sys.stderr, flush=True)
    uvicorn.run(logging_middleware(mcp.streamable_http_app()),
                host=HOST, port=PORT, log_level="warning")
