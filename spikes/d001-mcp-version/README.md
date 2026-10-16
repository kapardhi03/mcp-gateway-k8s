# D-001 spike: which MCP protocol version do real clients send?

Run 2026-10-16. This spike measures. It does not decide D-001.

Pre-registered expectations are in `docs/requirements-trace.md`, written before the spike ran.

## What was built

- `server.py` — hello-world MCP server over Streamable HTTP, one tool `echo(text)`, bound to `127.0.0.1:8765/mcp`. Raw ASGI middleware logs every request to `requests.jsonl` before the SDK sees it.
- `client_sdk.py` — a client using the same SDK, to prove it covers the client role. The gateway needs that: it is an MCP client to every upstream.
- `requirements.txt` — every version pinned.

## Versions

| Thing | Version | Source |
|---|---|---|
| MCP Python SDK (`mcp`) | 2.3.0, released 2026-10-02 | https://pypi.org/project/mcp/ |
| Docs | — | https://py.sdk.modelcontextprotocol.io/ |
| Python | 3.15.0 | local venv |
| Claude Code | 2.1.278 | `claude --version` |
| MCP Inspector | 2.11.0 | `npm view @modelcontextprotocol/inspector version` |
| Cursor | not installed | skipped |

Constants read from the installed SDK:

```
LATEST_PROTOCOL_VERSION    = 2026-07-28
MODERN_PROTOCOL_VERSIONS   = ('2026-07-28',)
DEFAULT_NEGOTIATED_VERSION = 2025-03-26
PROTOCOL_VERSION_META_KEY  = io.modelcontextprotocol/protocolVersion
headers                    = mcp-protocol-version, mcp-session-id
```

## Results

| Client | Client version | Protocol version | initialize | Session ID | echo worked |
|---|---|---|---|---|---|
| Claude Code | 2.1.278 | 2026-07-28 | no | no | not measured, see below |
| MCP Inspector (CLI) | 2.11.0 | 2025-11-25 | yes | yes | yes |
| Cursor | not installed | — | — | — | skipped |
| MCP Python SDK client | mcp 2.3.0 | 2026-07-28 | no | no | yes |

## What each client actually sent

**Claude Code 2.1.278 and the Python SDK, both on 2026-07-28.** No `initialize`. The first call is `server/discover`. No `Mcp-Session-Id` on any request. Version and client identity travel in `_meta` under `io.modelcontextprotocol/protocolVersion` and `io.modelcontextprotocol/clientInfo`, and each request carries `Mcp-Method`, plus `Mcp-Name` on a `tools/call`. Claude Code also calls `subscriptions/listen`, `prompts/list` and `resources/list` on connect.

**MCP Inspector 2.11.0, on 2025-11-25.** The full old handshake:

1. `POST initialize`, `protocolVersion: 2025-11-25` in params, no version header
2. `POST notifications/initialized`, now carrying `mcp-session-id`
3. `GET /mcp` to open the SSE stream
4. `POST tools/list`
5. `POST tools/call`

Every request after step 1 carried `mcp-session-id: bc705e1af...`.

## The finding that matters for D-001

**One SDK 2.3.0 server served both protocol versions at once, with no special handling.** It answered Claude Code and the Python SDK statelessly on 2026-07-28, and in the same process gave the Inspector an old-style session on 2025-11-25.

This bears directly on the D-001 options:

- **Option A** (gateway speaks only 2026-07-28) would break MCP Inspector 2.11.0 as it ships today. The Definition of Done names the Inspector as an acceptable external client.
- **Option C** (accept both) is what the SDK already does by default on the server side. It is not extra work; it is the out-of-the-box behaviour.

The stateless benefit that option A was supposed to buy for multi-replica gateways still applies to the clients that use 2026-07-28, because those send no session ID at all.

## Caveat: the Claude Code echo call

Claude Code connected, discovered and listed tools, which is what the protocol columns above record. The `tools/call` was not completed because a nested `claude -p` run from inside this session failed with `OAuth session expired and could not be refreshed`. That is a limitation of running Claude Code inside Claude Code, not a protocol or server problem. To finish the row, run from a normal terminal:

```bash
cd spikes/d001-mcp-version
./.venv/bin/python server.py &
claude mcp add --transport http d001-spike http://127.0.0.1:8765/mcp
# then in an interactive claude session, ask it to call the d001-spike echo tool
```

## Reproducing

```bash
cd spikes/d001-mcp-version
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python server.py          # terminal 1
./.venv/bin/python client_sdk.py      # terminal 2
npx -y @modelcontextprotocol/inspector --cli http://127.0.0.1:8765/mcp \
  --method tools/call --tool-name echo --tool-arg text="hello"
```

`requests.jsonl` is the evidence. It is committed as captured.
