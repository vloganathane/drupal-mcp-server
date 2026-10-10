"""Unit tests for authentication."""
from drupal_mcp_server.auth import AuthManager, BasicAuth, TokenAuth


def test_basic_auth_headers():
    auth = BasicAuth("admin", "secret")
    headers = auth.get_headers()
    assert "Authorization" in headers
    assert headers["Authorization"].startswith("Basic ")


def test_token_auth_headers():
    auth = TokenAuth("my-token-123")
    headers = auth.get_headers()
    assert headers["Authorization"] == "Bearer my-token-123"


def test_auth_manager_basic():
    settings = MagicMock()
    settings.DRUPAL_USERNAME = "admin"
    settings.DRUPAL_PASSWORD = "secret"
    settings.DRUPAL_OAUTH_CLIENT_ID = None
    
    manager = AuthManager(settings)
    headers = manager.get_headers()
    assert "Authorization" in headers


def test_auth_manager_no_auth():
    settings = MagicMock()
    settings.DRUPAL_USERNAME = None
    settings.DRUPAL_PASSWORD = None
    settings.DRUPAL_OAUTH_CLIENT_ID = None
    
    manager = AuthManager(settings)
    headers = manager.get_headers()
    assert headers == {}


from unittest.mock import MagicMock
