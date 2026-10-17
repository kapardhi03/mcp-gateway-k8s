"""Turning an upstream tool into a tool this gateway can serve.

Two halves, and both are needed:

1. A synthesised Python signature matching the upstream's JSON schema. The
   SDK derives its argument validator from the signature, so without this a
   proxied call fails validation before it is ever routed.
2. The upstream's EXACT schema pinned onto the registered tool afterwards, so
   clients see the real descriptions, enums and defaults rather than the
   lossy one derived from Python annotations.

Measured 2026-10-17 against SDK 2.3.0: passing `**kwargs` and overriding the
schema alone does not work (validation demands a literal `kwargs` field), and
clearing the validator makes the call crash. Doing both halves works, and
rejects a missing required argument.
"""

from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable

SEPARATOR = "__"

JSON_TO_PY: dict[str, Any] = {
    "integer": int,
    "number": float,
    "string": str,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def qualified(slug: str, tool: str) -> str:
    """D-009: always prefix. `<slug>__<tool>`, never conditionally."""
    return "%s%s%s" % (slug, SEPARATOR, tool)


def split(qualified_name: str) -> tuple[str, str] | None:
    """Inverse of qualified(). None when the name carries no slug."""
    slug, sep, tool = qualified_name.partition(SEPARATOR)
    if not sep or not slug or not tool:
        return None
    return slug, tool


def build_proxy_fn(
    public_name: str,
    schema: dict[str, Any] | None,
    sink: Callable[[str, dict[str, Any]], Awaitable[Any]],
) -> Callable[..., Awaitable[Any]]:
    """An async callable whose signature mirrors `schema`.

    Optional parameters default to None. Those defaults are stripped before
    the call leaves the gateway, in `strip_unset`, so an upstream never
    receives `note: null` for an argument the caller simply omitted.
    """
    props = (schema or {}).get("properties") or {}
    required = set((schema or {}).get("required") or [])

    params: list[inspect.Parameter] = []
    for pname, pspec in props.items():
        ann = JSON_TO_PY.get((pspec or {}).get("type"), Any)
        if pname in required:
            params.append(inspect.Parameter(pname, inspect.Parameter.KEYWORD_ONLY, annotation=ann))
        else:
            opt = Any if ann is Any else (ann | None)
            params.append(inspect.Parameter(pname, inspect.Parameter.KEYWORD_ONLY,
                                            annotation=opt, default=None))

    async def impl(**kwargs: Any) -> Any:
        return await sink(public_name, strip_unset(kwargs, required))

    impl.__signature__ = inspect.Signature(params)  # type: ignore[attr-defined]
    impl.__name__ = public_name.replace(SEPARATOR, "_")
    impl.__annotations__ = {p.name: p.annotation for p in params}
    return impl


def strip_unset(args: dict[str, Any], required: set[str]) -> dict[str, Any]:
    """Drop optional arguments the caller never supplied.

    The synthesised signature gives every optional parameter a default of
    None, so an omitted argument arrives as an explicit None. Forwarding that
    would tell the upstream "set this to null", which is a different request.
    Required parameters are passed through untouched, nulls included.
    """
    return {k: v for k, v in args.items() if k in required or v is not None}
