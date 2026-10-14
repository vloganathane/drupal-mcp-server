"""Authentication managers for Drupal MCP Server."""

from typing import Any

from .basic import BasicAuth
from .mcp_oauth import DrupalOAuthProvider
from .session import SessionAuth
from .token import TokenAuth


class AuthManager:
    """Selects and wraps auth strategy from settings."""

    def __init__(self, settings: Any):
        self._auth: Any | None = None
        self._session: Any | None = None
        self._basic: BasicAuth | None = None

        if settings.DRUPAL_OAUTH_TOKEN_URL:
            self._auth = TokenAuth(self._fetch_oauth_token(settings))
        elif settings.DRUPAL_USERNAME and settings.DRUPAL_PASSWORD:
            # Session auth covers both reads and writes; basic auth alone is
            # rejected with 403 on Drupal's mutating endpoints. Basic remains
            # as a fallback for sites without /user/login so reads still work.
            self._basic = BasicAuth(settings.DRUPAL_USERNAME, settings.DRUPAL_PASSWORD)
            self._session = SessionAuth(
                base_url=settings.DRUPAL_BASE_URL,
                username=settings.DRUPAL_USERNAME,
                password=settings.DRUPAL_PASSWORD,
                verify_ssl=bool(getattr(settings, "DRUPAL_VERIFY_SSL", True)),
            )
            self._auth = self._session

    async def ensure_session(self) -> None:
        """Log in and cache a CSRF token. Safe to call more than once."""
        if self._session is not None and not self._session.is_logged_in():
            await self._session.login()

    def get_session_cookies(self) -> dict[str, str]:
        """Session cookies for mutating requests, or {} if not using session auth."""
        if self._session is None:
            return {}
        return self._session.get_cookies()

    def _fetch_oauth_token(self, settings: Any) -> str:
        """Fetch OAuth token from the configured token URL."""
        import httpx
        try:
            resp = httpx.post(
                settings.DRUPAL_OAUTH_TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.DRUPAL_OAUTH_CLIENT_ID or "",
                    "client_secret": settings.DRUPAL_OAUTH_CLIENT_SECRET or "",
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json().get("access_token", "")
        except Exception:
            return ""

    def get_headers(self) -> dict[str, str]:
        """Return request headers for the active auth strategy.

        Synchronous to match the underlying strategies and the sync call site in
        ``clients/base.py::_headers``.

        When session auth is configured but not (yet) logged in, fall back to
        basic auth rather than sending an unauthenticated request.
        """
        if self._session is not None and not self._session.is_logged_in():
            if self._basic is not None:
                return self._basic.get_headers()
            return {}
        if self._auth:
            return self._auth.get_headers()
        return {}

    def get_mcp_oauth_provider(self, settings: Any) -> DrupalOAuthProvider | None:
        """Get OAuth provider for MCP HTTP transport."""
        if settings.MCP_TRANSPORT in ("http", "sse", "streamable-http"):
            base_url = f"http://{settings.MCP_HOST}:{settings.MCP_PORT}"
            return DrupalOAuthProvider(
                base_url=base_url,
                client_id=settings.DRUPAL_OAUTH_CLIENT_ID,
                client_secret=settings.DRUPAL_OAUTH_CLIENT_SECRET,
                token_url=settings.DRUPAL_OAUTH_TOKEN_URL,
            )
        return None
