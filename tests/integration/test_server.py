"""Integration tests for the full server."""

import asyncio
from typing import Any

from drupal_mcp_server.server import _input_schema_of, create_server


def test_server_import():
    from drupal_mcp_server.server import create_server as cs

    assert callable(cs)


def test_every_registered_tool_carries_a_usable_schema() -> None:
    """`/mcp/tools/list` returned `input_schema: {}` for all 366 tools.

    FastMCP's `FunctionTool` names the field `parameters`, while the code
    probed `inputSchema` and `input_schema` only, so every client reading
    that endpoint got an empty schema and could not build a request.
    """
    tools = asyncio.run(create_server().list_tools())

    assert len(tools) > 300, "tool registration regressed"
    broken = [t.name for t in tools if not _input_schema_of(t)]
    assert broken == [], f"{len(broken)} tools have no input schema: {broken[:5]}"


def test_schema_reads_every_name_the_sdk_has_used() -> None:
    class FunctionTool:
        parameters: dict[str, Any] = {"type": "object", "properties": {"a": {}}}

    class OldClientTool:
        inputSchema: dict[str, Any] = {"type": "object", "properties": {"b": {}}}

    class NewClientTool:
        input_schema: dict[str, Any] = {"type": "object", "properties": {"c": {}}}

    assert _input_schema_of(FunctionTool())["properties"].keys() == {"a"}
    assert _input_schema_of(OldClientTool())["properties"].keys() == {"b"}
    assert _input_schema_of(NewClientTool())["properties"].keys() == {"c"}
    assert _input_schema_of(object()) == {}


def test_tool_names_are_unique() -> None:
    """Two tools registering the same name silently shadow each other."""
    tools = asyncio.run(create_server().list_tools())
    names = [t.name for t in tools]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    assert duplicates == []


def test_every_tool_is_documented() -> None:
    """An empty description leaves an LLM guessing what the tool does."""
    tools = asyncio.run(create_server().list_tools())
    undocumented = [t.name for t in tools if not (t.description or "").strip()]
    assert undocumented == [], f"{len(undocumented)} tools lack a description"


def test_required_parameters_are_declared_in_properties() -> None:
    """A `required` entry with no matching property is unsatisfiable, so a
    client could never construct a valid call for that tool."""
    tools = asyncio.run(create_server().list_tools())
    broken = []
    for tool in tools:
        schema = _input_schema_of(tool)
        for name in schema.get("required") or []:
            if name not in (schema.get("properties") or {}):
                broken.append(f"{tool.name}.{name}")
    assert broken == []


def test_http_transport_hands_auth_to_the_server_not_to_run(monkeypatch) -> None:
    """`run(auth=...)` never bound a socket, so only stdio ever worked.

    FastMCP forwards unknown keywords from `run()` straight into
    `run_http_async()`, which has no `auth` parameter. Every http, sse and
    streamable-http start therefore died with
    ``TypeError: unexpected keyword argument 'auth'`` before uvicorn launched.
    FastMCP reads the provider off ``self.auth`` when it builds the HTTP app.
    """
    import fastmcp

    from drupal_mcp_server.auth import AuthManager
    from drupal_mcp_server.config import get_settings
    from drupal_mcp_server.server import run_server

    captured: dict[str, Any] = {}

    async def fake_ensure_session(self: Any) -> None:
        return None

    def fake_run(self: Any, **kwargs: Any) -> None:
        captured.update(kwargs)
        captured["_self_auth"] = getattr(self, "auth", None)

    monkeypatch.setattr(AuthManager, "ensure_session", fake_ensure_session)
    monkeypatch.setattr(fastmcp.FastMCP, "run", fake_run)

    # get_settings() is lru_cached, and an earlier test in this file already
    # built it before MCP_TRANSPORT was set - without clearing it the provider
    # is decided from a stale stdio setting.
    get_settings.cache_clear()
    monkeypatch.setenv("MCP_TRANSPORT", "http")
    try:
        run_server()
    finally:
        get_settings.cache_clear()

    assert "auth" not in captured, (
        "run(auth=...) is forwarded to run_http_async() and raises TypeError, "
        "so the HTTP transport never starts"
    )
    assert captured.get("_self_auth") is not None, (
        "the OAuth provider was never installed on the server, so the HTTP "
        "endpoint would serve without authentication"
    )
    # The path FastMCP actually mounts is derived, not the transport name.
    assert captured.get("path") == "/mcp"
