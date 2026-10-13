"""Unit tests for auth strategies."""


def test_auth_manager_init():
    from drupal_mcp_server.auth import AuthManager
    assert AuthManager is not None
