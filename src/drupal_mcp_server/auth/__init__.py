"""Authentication managers for Drupal MCP Server."""

from typing import Any

from .basic import BasicAuth
from .mcp_oauth import DrupalOAuthProvider
from .token import TokenAuth


class AuthManager:
    """Selects and wraps auth strategy from settings."""

    def __init__(self, settings: Any):
        self._auth: Any | None = None
        if settings.DRUPAL_USERNAME and settings.DRUPAL_PASSWORD:
            self._auth = BasicAuth(settings.DRUPAL_USERNAME, settings.DRUPAL_PASSWORD)
        elif settings.DRUPAL_OAUTH_TOKEN_URL:
            # For token-based auth — fetch token from OAuth token URL
            self._auth = TokenAuth(self._fetch_oauth_token(settings))

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
        """
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
