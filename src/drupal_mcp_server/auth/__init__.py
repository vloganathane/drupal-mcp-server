"""Authentication managers for Drupal MCP Server."""

from typing import Any

from .basic import BasicAuth
from .oauth import OAuth2Auth


class AuthManager:
    """Selects and wraps auth strategy from settings."""

    def __init__(self, settings: Any):
        self._auth: Any | None = None
        if settings.DRUPAL_USERNAME and settings.DRUPAL_PASSWORD:
            self._auth = BasicAuth(settings.DRUPAL_USERNAME, settings.DRUPAL_PASSWORD)
        elif (
            settings.DRUPAL_OAUTH_CLIENT_ID
            and settings.DRUPAL_OAUTH_CLIENT_SECRET
            and settings.DRUPAL_OAUTH_TOKEN_URL
        ):
            self._auth = OAuth2Auth(
                settings.DRUPAL_OAUTH_CLIENT_ID,
                settings.DRUPAL_OAUTH_CLIENT_SECRET,
                settings.DRUPAL_OAUTH_TOKEN_URL,
            )

    async def get_headers(self) -> dict[str, str]:
        if self._auth:
            headers = self._auth.get_headers()
            # Fetch OAuth token on first use if needed
            if hasattr(self._auth, "_access_token") and self._auth._access_token is None:
                await self._auth._fetch_token()
                headers = self._auth.get_headers()
            return headers  # type: ignore[no-any-return]
        return {}
