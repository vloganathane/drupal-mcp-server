"""Integration tests for the full server."""


def test_server_import():
    from drupal_mcp_server.server import create_server
    assert callable(create_server)
