"""Unit tests for auth strategies."""

from typing import Any

import pytest


def test_auth_manager_init():
    from drupal_mcp_server.auth import AuthManager
    assert AuthManager is not None


class FakeSettings:
    DRUPAL_BASE_URL = "https://example.test"
    DRUPAL_USERNAME = "admin"
    DRUPAL_PASSWORD = "secret"
    DRUPAL_VERIFY_SSL = True
    DRUPAL_OAUTH_TOKEN_URL = None
    DRUPAL_OAUTH_CLIENT_ID = None
    DRUPAL_OAUTH_CLIENT_SECRET = None
    MCP_TRANSPORT = "stdio"
    MCP_HOST = "127.0.0.1"
    MCP_PORT = 8000


def test_auth_manager_uses_session_auth_for_credentials():
    """Basic auth alone is rejected with 403 on Drupal's write endpoints."""
    from drupal_mcp_server.auth import AuthManager

    manager = AuthManager(FakeSettings())

    assert manager._session is not None


def test_no_session_cookies_before_login():
    from drupal_mcp_server.auth import AuthManager

    manager = AuthManager(FakeSettings())

    assert manager.get_session_cookies() == {}


def test_falls_back_to_basic_auth_when_not_logged_in():
    """Sending no Authorization header at all would break reads on sites
    where /user/login is unavailable."""
    from drupal_mcp_server.auth import AuthManager

    manager = AuthManager(FakeSettings())
    headers = manager.get_headers()

    assert headers["Authorization"].startswith("Basic ")


def test_session_headers_include_csrf_token():
    from drupal_mcp_server.auth.session import SessionAuth

    auth = SessionAuth("https://example.test", "admin", "secret")
    assert auth.get_headers() == {}  # not logged in yet
    assert auth.is_logged_in() is False

    auth._logged_in = True
    auth._csrf = "abc123"
    auth._cookies = {"SSESS123": "value"}

    assert auth.get_headers() == {"X-CSRF-Token": "abc123"}
    assert auth.get_cookies() == {"SSESS123": "value"}


class _FakeAsyncClient:
    """Stands in for httpx.AsyncClient during a scripted login."""

    cookie_value = "SSESSxyz"

    def __init__(self, *args: Any, **kwargs: Any):
        self.cookies: dict[str, str] = {}

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def post(self, url: str, **kwargs: Any) -> Any:
        assert url.endswith("/user/login")
        body = kwargs.get("data") or {}
        if body.get("pass") != "secret":
            return _Resp(403, "")
        self.cookies = {self.cookie_value: "1"}
        return _Resp(200, "")

    async def get(self, url: str, **kwargs: Any) -> Any:
        assert url.endswith("/session/token")
        return _Resp(200, "csrf-token-xyz")


class _Resp:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


@pytest.mark.asyncio
async def test_session_login_fetches_cookie_and_csrf(monkeypatch: pytest.MonkeyPatch):
    import drupal_mcp_server.auth.session as session_mod

    monkeypatch.setattr(session_mod.httpx, "AsyncClient", _FakeAsyncClient)

    auth = session_mod.SessionAuth("https://example.test", "admin", "secret")
    await auth.login()

    assert auth.is_logged_in() is True
    assert auth.get_cookies() == {"SSESSxyz": "1"}
    assert auth.get_headers() == {"X-CSRF-Token": "csrf-token-xyz"}


@pytest.mark.asyncio
async def test_session_login_rejects_bad_credentials(monkeypatch: pytest.MonkeyPatch):
    import drupal_mcp_server.auth.session as session_mod

    monkeypatch.setattr(session_mod.httpx, "AsyncClient", _FakeAsyncClient)

    auth = session_mod.SessionAuth("https://example.test", "admin", "wrong")

    with pytest.raises(RuntimeError, match="login failed"):
        await auth.login()
    assert auth.is_logged_in() is False


@pytest.mark.asyncio
async def test_session_login_requires_a_cookie(monkeypatch: pytest.MonkeyPatch):
    """A site without /user/login must fail loudly, not run unauthenticated."""
    import drupal_mcp_server.auth.session as session_mod

    class NoCookieClient(_FakeAsyncClient):
        async def post(self, url: str, **kwargs: Any) -> Any:
            return _Resp(200, "")  # 200 but no session established

    monkeypatch.setattr(session_mod.httpx, "AsyncClient", NoCookieClient)

    auth = session_mod.SessionAuth("https://example.test", "admin", "secret")

    with pytest.raises(RuntimeError, match="no session cookie"):
        await auth.login()
