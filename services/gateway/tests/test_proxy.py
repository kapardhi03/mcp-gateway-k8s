"""Tool-name prefixing (D-009) and the proxy mechanism."""
from __future__ import annotations

import json

import pytest
from mcp.server import MCPServer

from gateway import proxy

SCHEMA = {
    "type": "object",
    "properties": {
        "order_id": {"type": "integer", "description": "the id"},
        "status": {"type": "string", "enum": ["processing", "completed"],
                   "description": "new status"},
        "note": {"type": "string", "description": "optional note"},
    },
    "required": ["order_id", "status"],
}


# --------------------------------------------------- D-009 naming

def test_qualified_always_prefixes():
    assert proxy.qualified("woo", "list_orders") == "woo__list_orders"


def test_split_is_the_inverse():
    assert proxy.split("woo__list_orders") == ("woo", "list_orders")


@pytest.mark.parametrize("bad", ["noseparator", "__leading", "trailing__", "", "__"])
def test_split_rejects_unprefixed_names(bad):
    assert proxy.split(bad) is None


def test_names_satisfy_the_spec_character_rule():
    """Both spec versions: A-Z a-z 0-9 underscore hyphen dot, 1 to 128 chars.

    The scheme deliberately stays inside letters, digits and underscores so it
    also survives the stricter ^[a-zA-Z0-9_]{1,64}$ some clients enforce.
    """
    import re
    for slug, tool in [("woo", "update_order_status"), ("fx", "convert")]:
        name = proxy.qualified(slug, tool)
        assert re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", name), name
        assert re.fullmatch(r"[a-zA-Z0-9_]{1,64}", name), name


# --------------------------------------------------- optional-arg stripping

def test_strip_unset_drops_omitted_optionals():
    args = {"order_id": 12, "status": "completed", "note": None}
    assert proxy.strip_unset(args, {"order_id", "status"}) == {
        "order_id": 12, "status": "completed"}


def test_strip_unset_keeps_required_nulls():
    """A required parameter explicitly set to null is a real value, not an omission."""
    args = {"order_id": None, "status": "completed"}
    assert proxy.strip_unset(args, {"order_id", "status"}) == args


# --------------------------------------------------- the proxy mechanism

async def test_proxy_preserves_the_upstream_schema_exactly():
    """REGRESSION. The reason build_proxy_fn exists.

    Measured against SDK 2.3.0: the SDK derives its argument validator from
    the Python signature, so a `**kwargs` passthrough fails validation, and
    clearing the validator crashes the call. Synthesising a real signature
    makes validation work, but the schema the SDK then derives is lossy: it
    loses enums and descriptions. So the exact upstream schema is pinned back
    on afterwards. This test fails if either half is dropped.
    """
    captured: dict = {}

    async def sink(name, args):
        captured["name"], captured["args"] = name, args
        return {"ok": True}

    mcp = MCPServer("gw-test", version="0.0.1")
    name = proxy.qualified("woo", "update_order_status")
    fn = proxy.build_proxy_fn(name, SCHEMA, sink)
    mcp.add_tool(fn, name=name, description="proxied")
    mcp._tool_manager.get_tool(name).parameters = SCHEMA

    served = (await mcp.list_tools())[0].input_schema
    # the lossy derived schema would have neither of these
    assert served["properties"]["status"]["enum"] == ["processing", "completed"]
    assert served["properties"]["order_id"]["description"] == "the id"

    await mcp.call_tool(name, {"order_id": 12, "status": "completed"})
    assert captured["name"] == name
    assert captured["args"] == {"order_id": 12, "status": "completed"}
    assert "note" not in captured["args"], "omitted optional was forwarded as null"


async def test_proxy_rejects_a_missing_required_argument():
    async def sink(name, args):
        raise AssertionError("must not reach the upstream")

    mcp = MCPServer("gw-test", version="0.0.1")
    name = proxy.qualified("woo", "update_order_status")
    mcp.add_tool(proxy.build_proxy_fn(name, SCHEMA, sink), name=name, description="p")
    mcp._tool_manager.get_tool(name).parameters = SCHEMA

    from mcp.server.mcpserver.exceptions import ToolError
    with pytest.raises(ToolError):
        await mcp.call_tool(name, {"status": "completed"})


async def test_proxy_handles_a_tool_with_no_parameters():
    async def sink(name, args):
        return {"args": args}

    mcp = MCPServer("gw-test", version="0.0.1")
    name = proxy.qualified("fx", "rates")
    empty = {"type": "object", "properties": {}}
    mcp.add_tool(proxy.build_proxy_fn(name, empty, sink), name=name, description="p")
    r = await mcp.call_tool(name, {})
    assert r.content


# --------------------------------------------- GW-5: useful failure reasons

def test_reason_unwraps_exception_groups():
    """REGRESSION, GW-5.

    anyio wraps transport failures in an ExceptionGroup, so reporting the
    outer type put the useless word "ExceptionGroup" in the Unreachable
    status an operator reads. Observed live when woo-mcp was scaled to 0.
    """
    from gateway.upstreams import _reason

    inner = ConnectionRefusedError("refused")
    group = ExceptionGroup("transport failed", [inner])
    assert _reason(group) == "ConnectionRefusedError"
    assert _reason(inner) == "ConnectionRefusedError"
    # nested groups still resolve
    assert _reason(ExceptionGroup("outer", [group])) == "ConnectionRefusedError"


def test_reason_never_returns_the_message():
    """The text of a transport error can quote request headers."""
    from gateway.upstreams import _reason

    assert _reason(RuntimeError("Bearer SUPER-SECRET-TOKEN")) == "RuntimeError"
