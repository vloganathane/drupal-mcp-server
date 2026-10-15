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
    """A site without /user/login must fail loudly, not run unauthenticated.

    This check is also what rejects bad credentials: Drupal answers a refused
    login with 200 re-rendering the form and sets no cookie, so no status code
    above can catch it.
    """
    import drupal_mcp_server.auth.session as session_mod

    class NoCookieClient(_FakeAsyncClient):
        async def post(self, url: str, **kwargs: Any) -> Any:
            return _Resp(200, "Sorry, unrecognized username or password")

    monkeypatch.setattr(session_mod.httpx, "AsyncClient", NoCookieClient)

    auth = session_mod.SessionAuth("https://example.test", "admin", "wrong")

    with pytest.raises(RuntimeError, match="no session cookie"):
        await auth.login()


@pytest.mark.asyncio
async def test_a_redirecting_login_is_a_successful_login(
    monkeypatch: pytest.MonkeyPatch,
):
    """Drupal answers a good login with 303 to the account page, and builds
    that Location from the scheme *it* saw the request arrive on.

    Following it used to turn a working login into a failure: the site
    reported itself as plain `http` while the client was on HTTPS, so the
    redirect was fetched as HTTP against a TLS port, nginx answered 400, and
    the cookie the same response had just issued was discarded. Session auth
    then stayed off, and every write silently fell back to basic auth, which
    Drupal's mutating endpoints reject.
    """
    import drupal_mcp_server.auth.session as session_mod

    class _RedirectingClient(_FakeAsyncClient):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            assert kwargs.get("follow_redirects") is False, (
                "the login POST must not be followed to a URL the site invented"
            )

        async def post(self, url: str, **kwargs: Any) -> Any:
            assert url.endswith("/user/login")
            self.cookies = {self.cookie_value: "1"}
            return _Resp(303, "")

    monkeypatch.setattr(session_mod.httpx, "AsyncClient", _RedirectingClient)

    auth = session_mod.SessionAuth("https://example.test", "admin", "secret")
    await auth.login()

    assert auth.is_logged_in() is True
    assert auth.get_cookies() == {"SSESSxyz": "1"}
    assert auth.get_headers() == {"X-CSRF-Token": "csrf-token-xyz"}


def test_bearer_token_is_used_when_no_credentials_are_set():
    """DRUPAL_API_TOKEN was documented in three places but never wired up,
    so setting it silently sent unauthenticated requests."""
    from drupal_mcp_server.auth import AuthManager

    class TokenSettings(FakeSettings):
        DRUPAL_USERNAME = None
        DRUPAL_PASSWORD = None
        DRUPAL_API_TOKEN = "tok-abc123"

    headers = AuthManager(TokenSettings()).get_headers()

    assert headers["Authorization"] == "Bearer tok-abc123"
    assert AuthManager(TokenSettings())._session is None


def test_credentials_take_priority_over_a_bearer_token():
    from drupal_mcp_server.auth import AuthManager

    class BothSettings(FakeSettings):
        DRUPAL_API_TOKEN = "tok-abc123"

    manager = AuthManager(BothSettings())

    assert manager._session is not None
    assert manager.get_headers()["Authorization"].startswith("Basic ")


def test_no_auth_at_all_yields_no_authorization_header():
    from drupal_mcp_server.auth import AuthManager

    class Anonymous(FakeSettings):
        DRUPAL_USERNAME = None
        DRUPAL_PASSWORD = None
        DRUPAL_OAUTH_TOKEN_URL = None
        DRUPAL_API_TOKEN = None

    assert "Authorization" not in AuthManager(Anonymous()).get_headers()
