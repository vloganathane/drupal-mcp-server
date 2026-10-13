"""Authentication managers for Drupal MCP Server."""

from typing import Any

from .basic import BasicAuth
from .token import TokenAuth
from .mcp_oauth import DrupalOAuthProvider


class AuthManager:
    """Selects and wraps auth strategy from settings."""

    def __init__(self, settings: Any):
        self._auth: Any | None = None
        if settings.DRUPAL_USERNAME and settings.DRUPAL_PASSWORD:
            self._auth = BasicAuth(settings.DRUPAL_USERNAME, settings.DRUPAL_PASSWORD)
        elif settings.DRUPAL_OAUTH_TOKEN_URL:
            # For token-based auth
            self._auth = TokenAuth("")  # Will be set via _fetch_token

    async def get_headers(self) -> dict[str, str]:
        if self._auth:
            headers = self._auth.get_headers()
            return headers  # type: ignore[no-any-return]
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
