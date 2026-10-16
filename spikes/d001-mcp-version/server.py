"""D-001 spike server.

Hello-world MCP server over Streamable HTTP with one tool, echo(text).
Bound to 127.0.0.1 only.

Every HTTP request is logged to requests.jsonl before the SDK handles it:
timestamp, HTTP method, MCP-Protocol-Version, Mcp-Session-Id, Mcp-Method,
Mcp-Name, the JSON-RPC method, and any _meta or clientInfo in the body.

The point is to measure what real clients actually send. Nothing here
decides D-001.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from mcp.server import MCPServer

HERE = Path(__file__).resolve().parent
LOG_PATH = HERE / "requests.jsonl"

HOST = "127.0.0.1"
PORT = 8765
PATH = "/mcp"

mcp = MCPServer("d001-spike", version="0.1.0")


@mcp.tool()
def echo(text: str) -> str:
    """Return the text it was given."""
    return text


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _extract(body: bytes) -> dict[str, Any]:
    """Pull the interesting bits out of a JSON-RPC body without assuming shape."""
    out: dict[str, Any] = {}
    if not body:
        return out
    try:
        parsed = json.loads(body)
    except Exception:
        out["body_parse_error"] = True
        out["body_prefix"] = body[:200].decode("utf-8", "replace")
        return out

    msgs = parsed if isinstance(parsed, list) else [parsed]
    methods, metas, clients = [], [], []
    for m in msgs:
        if not isinstance(m, dict):
            continue
        if m.get("method"):
            methods.append(m["method"])
        if isinstance(m.get("_meta"), dict):
            metas.append(m["_meta"])
        params = m.get("params")
        if isinstance(params, dict):
            if isinstance(params.get("_meta"), dict):
                metas.append(params["_meta"])
            if isinstance(params.get("clientInfo"), dict):
                clients.append(params["clientInfo"])
            if params.get("protocolVersion"):
                out["params_protocolVersion"] = params["protocolVersion"]
    if methods:
        out["jsonrpc_methods"] = methods
    if metas:
        out["_meta"] = metas
    if clients:
        out["clientInfo"] = clients
    return out


def logging_middleware(app):
    """Raw ASGI middleware. Buffers the body so the app still receives it."""

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

        record: dict[str, Any] = {
            "ts": _utcnow(),
            "http_method": scope.get("method"),
            "path": scope.get("path"),
            "mcp_protocol_version": headers.get("mcp-protocol-version"),
            "mcp_session_id": headers.get("mcp-session-id"),
            "mcp_method": headers.get("mcp-method"),
            "mcp_name": headers.get("mcp-name"),
            "accept": headers.get("accept"),
            "content_type": headers.get("content-type"),
            "user_agent": headers.get("user-agent"),
        }
        record.update(_extract(body))

        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        print(
            f"[req] {record['http_method']} {record['path']} "
            f"proto={record['mcp_protocol_version']} "
            f"session={record['mcp_session_id']} "
            f"mcp-method={record['mcp_method']} "
            f"rpc={record.get('jsonrpc_methods')}",
            file=sys.stderr,
            flush=True,
        )

        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await app(scope, replay, send)

    return wrapped


def main() -> None:
    app = mcp.streamable_http_app(streamable_http_path=PATH, host=HOST)
    print(f"[spike] listening on http://{HOST}:{PORT}{PATH}", file=sys.stderr, flush=True)
    print(f"[spike] logging to {LOG_PATH}", file=sys.stderr, flush=True)
    uvicorn.run(logging_middleware(app), host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
