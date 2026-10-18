"""Unit tests for the networked-transport auth guard.

The tool surface executes drush, composer and shell commands, so binding an
HTTP transport without authentication is a remote code execution endpoint.
These tests pin the refusal and its two escape hatches.
"""

from typing import Any

import pytest

from drupal_mcp_server.server import _require_network_auth


class FakeSettings:
    """Only the fields the guard reads."""

    DRUPAL_OAUTH_CLIENT_ID: Any = None
    MCP_ALLOW_INSECURE_HTTP = False


def test_stdio_is_not_affected():
    _require_network_auth(FakeSettings(), "stdio")  # must not raise


@pytest.mark.parametrize("transport", ["http", "sse", "streamable-http"])
def test_network_transport_without_auth_refuses(transport: str):
    with pytest.raises(SystemExit, match="MCP_ALLOW_INSECURE_HTTP"):
        _require_network_auth(FakeSettings(), transport)


def test_oauth_client_allows_network_transport():
    settings = FakeSettings()
    settings.DRUPAL_OAUTH_CLIENT_ID = "mcp-client"
    _require_network_auth(settings, "http")  # must not raise


def test_explicit_insecure_flag_allows_network_transport():
    settings = FakeSettings()
    settings.MCP_ALLOW_INSECURE_HTTP = True
    _require_network_auth(settings, "http")  # must not raise


def test_opt_in_via_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MCP_ALLOW_INSECURE_HTTP", "1")
    _require_network_auth(FakeSettings(), "http")  # must not raise


def test_refusal_says_what_to_do():
    with pytest.raises(SystemExit) as excinfo:
        _require_network_auth(FakeSettings(), "http")
    message = str(excinfo.value)
    assert "DRUPAL_OAUTH_CLIENT_ID" in message
    assert "stdio" in message
