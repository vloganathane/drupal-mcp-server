"""Unit tests for auth strategies."""

import time
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


class _OAuthClient:
    """The only attribute every provider method reads off a client."""

    client_id = "client-1"


def _provider() -> Any:
    from drupal_mcp_server.auth.mcp_oauth import DrupalOAuthProvider

    return DrupalOAuthProvider(base_url="https://example.test")


async def _issue(provider: Any, scopes: list[str]) -> Any:
    params = type(
        "P",
        (),
        {
            "redirect_uri": "https://example.test/callback",
            "code_challenge": None,
            "scopes": scopes,
        },
    )()
    redirect = await provider.authorize(_OAuthClient(), params)
    return await provider.exchange_authorization_code(
        _OAuthClient(), str(redirect).split("code=")[1]
    )


@pytest.mark.asyncio
async def test_an_issued_token_is_accepted_on_the_next_request() -> None:
    """The fail-closed side was the only half of this ever observed.

    `load_access_token` returned the dict the token had been stored in, so
    FastMCP's `.scopes` and `.client_id` reads raised AttributeError and a
    perfectly good token was refused as harshly as a forged one. HTTP
    transport with OAuth enabled was therefore unusable for everyone, and the
    401 that produced looked exactly like security working. `expires_at` was
    stored as a float too, where `AccessToken.expires_at` is an int, so the
    model would have refused to validate even had the type been right.
    """
    from fastmcp.server.auth import AccessToken

    provider = _provider()
    token = await _issue(provider, ["drupal:read", "drupal:write"])
    loaded = await provider.load_access_token(token.access_token)

    assert isinstance(loaded, AccessToken), "a dict was returned where a token was promised"
    assert loaded.token == token.access_token
    assert loaded.client_id == "client-1"
    assert loaded.scopes == ["drupal:read", "drupal:write"]
    assert isinstance(loaded.expires_at, int)
    assert loaded.expires_at > time.time()


@pytest.mark.asyncio
async def test_an_expired_or_unknown_token_is_still_refused() -> None:
    """Acceptance has to be earned by the token, not bought by the fix.

    An expired one, a revoked one and a made-up one are each refused, so
    nothing about the positive path leaked into the negative one.
    """
    provider = _provider()

    revoked = await _issue(provider, ["drupal:read"])
    await provider.revoke_token(revoked.access_token)
    assert await provider.load_access_token(revoked.access_token) is None

    # The only way to reach expiry in-process: the token was issued to live
    # for an hour, and there is no clock to advance.
    expired = await _issue(provider, ["drupal:read"])
    provider._access_tokens[expired.access_token]["expires_at"] = int(time.time()) - 1
    assert await provider.load_access_token(expired.access_token) is None

    assert await provider.load_access_token("not-a-real-token") is None


@pytest.mark.asyncio
async def test_a_code_is_single_use_and_refresh_tokens_are_swapped() -> None:
    """Both exchanges answer an unseen value with an exception rather than a
    token, so a replayed code or a guessed refresh token gets nowhere."""
    provider = _provider()
    params = type(
        "P",
        (),
        {
            "redirect_uri": "https://example.test/callback",
            "code_challenge": None,
            "scopes": ["drupal:read"],
        },
    )()
    code = str(await provider.authorize(_OAuthClient(), params)).split("code=")[1]

    first = await provider.exchange_authorization_code(_OAuthClient(), code)
    with pytest.raises(ValueError, match="Invalid authorization code"):
        await provider.exchange_authorization_code(_OAuthClient(), code)

    second = await provider.exchange_refresh_token(
        _OAuthClient(), first.refresh_token, ["drupal:read", "drupal:write"]
    )
    assert second.access_token != first.access_token
    assert (await provider.load_access_token(second.access_token)).scopes == [
        "drupal:read",
        "drupal:write",
    ]

    with pytest.raises(ValueError, match="Invalid refresh token"):
        await provider.exchange_refresh_token(_OAuthClient(), "not-a-token", [])


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


def _outbound_settings() -> FakeSettings:
    """The settings shape that selects client-credentials auth."""

    class Outbound(FakeSettings):
        DRUPAL_OAUTH_TOKEN_URL = "https://example.test/oauth/token"
        DRUPAL_OAUTH_CLIENT_ID = "mcp-client"
        DRUPAL_OAUTH_CLIENT_SECRET = "mcp-secret"
        DRUPAL_USERNAME = None
        DRUPAL_PASSWORD = None

    return Outbound()


def test_client_credentials_leg_posts_the_configured_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`DRUPAL_OAUTH_TOKEN_URL` selects client-credentials auth, yet every
    other test sets it to None to reach the session path — so the grant
    that actually reaches Drupal, carrying these credentials, was never
    observed.
    """
    from drupal_mcp_server.auth import AuthManager

    posted: dict[str, Any] = {}

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"access_token": "tok-outbound"}

    def _post(url: str, *, data: dict[str, str], timeout: float) -> _Resp:
        posted.update({"url": url, "data": data, "timeout": timeout})
        return _Resp()

    monkeypatch.setattr("httpx.post", _post)
    manager = AuthManager(_outbound_settings())

    assert posted == {
        "url": "https://example.test/oauth/token",
        "data": {
            "grant_type": "client_credentials",
            "client_id": "mcp-client",
            "client_secret": "mcp-secret",
        },
        "timeout": 30.0,
    }
    assert manager.get_headers() == {"Authorization": "Bearer tok-outbound"}


def test_an_unreachable_token_endpoint_degrades_to_an_empty_bearer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Startup must not crash when Drupal is unreachable: the fetch
    swallows the failure and the leg degrades to an empty bearer rather
    than raising — the failure mode, pinned so it stays visible."""
    from drupal_mcp_server.auth import AuthManager

    def _post(*args: Any, **kwargs: Any) -> None:
        raise ConnectionError("connection refused")

    monkeypatch.setattr("httpx.post", _post)
    manager = AuthManager(_outbound_settings())

    assert manager.get_headers() == {"Authorization": "Bearer "}


def test_the_network_provider_ships_the_read_and_write_requirement() -> None:
    """The factory hands the socket the constructor default — pin it, so
    the guard cannot silently widen to "any authenticated token"."""
    from drupal_mcp_server.auth import AuthManager

    class Networked(FakeSettings):
        MCP_TRANSPORT = "http"
        DRUPAL_OAUTH_CLIENT_ID = "mcp-client"

    settings = Networked()
    provider = AuthManager(settings).get_mcp_oauth_provider(settings)

    assert provider is not None
    assert provider.required_scopes == ["drupal:read", "drupal:write"]


@pytest.mark.asyncio
async def test_loaded_codes_and_refresh_tokens_are_models_not_dicts() -> None:
    """The wire path hands the SDK's token handler whatever these loaders
    return, and it reads `.client_id`, `.expires_at`, `.redirect_uri` and
    `.code_challenge` off the result. The stored dicts answered with
    AttributeError and every over-the-wire /token request became a 500 —
    the third instance of the dict-versus-model shape (after
    load_access_token, and previously unnoticed because the exchanges were
    only ever driven with raw strings, which `str()` happens to pass
    through). Both exchanges must also accept the loaded models.
    """
    from drupal_mcp_server.auth.mcp_oauth import DrupalOAuthProvider

    provider = DrupalOAuthProvider(base_url="https://example.test")
    client_info = type("C", (), {"client_id": "client-1"})()
    params = type(
        "P",
        (),
        {
            "redirect_uri": "https://example.test/callback",
            "redirect_uri_provided_explicitly": True,
            "code_challenge": "challenge-xyz",
            "scopes": ["drupal:read", "drupal:write"],
        },
    )()
    redirect = await provider.authorize(client_info, params)
    code = str(redirect).split("code=")[1]

    loaded = await provider.load_authorization_code(client_info, code)
    assert loaded is not None
    assert loaded.code == code
    assert loaded.client_id == "client-1"
    assert loaded.scopes == ["drupal:read", "drupal:write"]
    assert loaded.code_challenge == "challenge-xyz"
    assert loaded.expires_at > time.time()
    assert str(loaded.redirect_uri) == "https://example.test/callback"
    assert loaded.redirect_uri_provided_explicitly is True

    token = await provider.exchange_authorization_code(client_info, loaded)
    assert token.access_token

    refresh_loaded = await provider.load_refresh_token(client_info, token.refresh_token)
    assert refresh_loaded is not None
    assert refresh_loaded.client_id == "client-1"
    assert refresh_loaded.scopes == ["drupal:read", "drupal:write"]

    refreshed = await provider.exchange_refresh_token(
        client_info, refresh_loaded, ["drupal:read", "drupal:write"]
    )
    assert refreshed.access_token
