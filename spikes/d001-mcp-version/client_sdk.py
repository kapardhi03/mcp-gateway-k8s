"""D-001 spike client.

Connects to the spike server over Streamable HTTP with the official MCP
Python SDK and calls echo once. This proves the SDK covers the client role,
which the gateway needs: it is an MCP client to every upstream.

Prints what the session negotiated so it can go in the results table.
"""

from __future__ import annotations

import asyncio
import json

from mcp.client import Client

URL = "http://127.0.0.1:8765/mcp"


async def main() -> None:
    async with Client(URL) as client:
        tools = await client.list_tools()
        result = await client.call_tool("echo", {"text": "hello from the python sdk"})

        info = getattr(client, "server_info", None)
        payload = {
            "negotiated_protocol_version": getattr(client, "protocol_version", None),
            "server_info": {
                "name": getattr(info, "name", None),
                "version": getattr(info, "version", None),
            }
            if info
            else None,
            "tools": [t.name for t in tools.tools],
            "echo_result": [getattr(c, "text", None) for c in result.content],
            "is_error": getattr(result, "isError", None),
        }
        print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
