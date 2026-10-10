"""Authentication managers for Drupal MCP Server."""
from typing import Any, Dict, Optional
from .basic import BasicAuth
from .token import TokenAuth
from .oauth import OAuth2Auth


class AuthManager:
    """Selects and wraps auth strategy from settings."""

    def __init__(self, settings: Any):
        self._auth: Optional[Any] = None
        if settings.DRUPAL_USERNAME and settings.DRUPAL_PASSWORD:
            self._auth = BasicAuth(settings.DRUPAL_USERNAME, settings.DRUPAL_PASSWORD)
        elif settings.DRUPAL_OAUTH_CLIENT_ID and settings.DRUPAL_OAUTH_CLIENT_SECRET and settings.DRUPAL_OAUTH_TOKEN_URL:
            self._auth = OAuth2Auth(
                settings.DRUPAL_OAUTH_CLIENT_ID,
                settings.DRUPAL_OAUTH_CLIENT_SECRET,
                settings.DRUPAL_OAUTH_TOKEN_URL,
            )

    def get_headers(self) -> Dict[str, str]:
        if self._auth:
            return self._auth.get_headers()
        return {}
