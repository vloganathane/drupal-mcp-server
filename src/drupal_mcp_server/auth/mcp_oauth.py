"""OAuth 2.1 authentication provider for FastMCP HTTP transport with per-session scopes."""

from typing import Any

from fastmcp.server.auth import AccessToken as FastMCPAccessToken
from fastmcp.server.auth import OAuthProvider
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCodeT,
    AuthorizationParams,
    RefreshTokenT,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken


class DrupalOAuthProvider(OAuthProvider):
    """OAuth 2.1 provider with Drupal integration and per-session scopes."""
    
    # Define available scopes
    SCOPES = {
        "drupal:read": "Read Drupal content and configuration",
        "drupal:write": "Create and update Drupal content",
        "drupal:admin": "Administrative access (config, modules, users)",
        "drupal:migrate": "Run migrations and analysis tools",
        "drupal:devops": "Execute Drush commands and manage infrastructure",
        "drupal:ai": "Use AI-powered tools",
        "drupal:security": "Run security audits and scans",
    }
    
    # Default scopes for different roles
    ROLE_SCOPES = {
        "anonymous": ["drupal:read"],
        "authenticated": ["drupal:read", "drupal:write"],
        "editor": ["drupal:read", "drupal:write"],
        "administrator": ["drupal:read", "drupal:write", "drupal:admin"],
        "migrator": ["drupal:read", "drupal:write", "drupal:migrate"],
        "devops": ["drupal:read", "drupal:write", "drupal:devops"],
        "security": ["drupal:read", "drupal:admin", "drupal:security"],
    }
    
    def __init__(
        self,
        base_url: str,
        client_id: str | None = None,
        client_secret: str | None = None,
        token_url: str | None = None,
        required_scopes: list[str] | None = None,
    ):
        super().__init__(
            base_url=base_url,
            required_scopes=required_scopes or ["drupal:read", "drupal:write"],
        )
        self._drupal_client_id = client_id
        self._drupal_client_secret = client_secret
        self._drupal_token_url = token_url
        self._access_tokens: dict[str, dict[str, Any]] = {}
        self._auth_codes: dict[str, dict[str, Any]] = {}
        self._refresh_tokens: dict[str, dict[str, Any]] = {}
        self._clients: dict[str, OAuthClientInformationFull] = {}
        # Per-session scopes: session_id -> list of scopes
        self._session_scopes: dict[str, list[str]] = {}
        # Session -> client mapping
        self._session_clients: dict[str, str] = {}
    
    def get_available_scopes(self) -> dict[str, str]:
        """Get all available scopes with descriptions."""
        return self.SCOPES.copy()
    
    def get_role_scopes(self, role: str) -> list[str]:
        """Get scopes for a role."""
        return self.ROLE_SCOPES.get(role, self.ROLE_SCOPES["authenticated"])
    
    def set_session_scopes(self, session_id: str, scopes: list[str]) -> None:
        """Set scopes for a session."""
        # Validate scopes
        valid_scopes = [s for s in scopes if s in self.SCOPES]
        self._session_scopes[session_id] = valid_scopes
    
    def get_session_scopes(self, session_id: str) -> list[str]:
        """Get scopes for a session."""
        return self._session_scopes.get(session_id, self.required_scopes)
    
    def set_session_client(self, session_id: str, client_id: str) -> None:
        """Associate a client with a session."""
        self._session_clients[session_id] = client_id
    
    def get_session_client(self, session_id: str) -> str | None:
        """Get client ID for a session."""
        return self._session_clients.get(session_id)
    
    def clear_session(self, session_id: str) -> None:
        """Clear session data."""
        self._session_scopes.pop(session_id, None)
        self._session_clients.pop(session_id, None)
    
    def get_challenge_scopes(self, required_scopes: list[str] | None = None) -> list[str]:
        """Get scopes for WWW-Authenticate challenge.
        
        This can be overridden to provide session-specific scopes.
        """
        # If we have session-specific scopes, use those
        # For now, use the default behavior
        return super().get_challenge_scopes(required_scopes)
    
    async def load_access_token(self, token: str) -> FastMCPAccessToken | None:
        """Load and validate an access token."""
        if token in self._access_tokens:
            token_data = self._access_tokens[token]
            # Check expiry
            import time
            if token_data.get("expires_at", 0) > time.time():
                return token_data  # type: ignore[return-value]
        return None
    
    async def load_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: str,
    ) -> AuthorizationCodeT | None:
        """Load an authorization code."""
        auth_code_str = str(authorization_code)
        return self._auth_codes.get(auth_code_str)  # type: ignore[return-value]
    
    async def load_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: str,
    ) -> RefreshTokenT | None:
        """Load a refresh token."""
        refresh_token_str = str(refresh_token)
        return self._refresh_tokens.get(refresh_token_str)  # type: ignore[return-value]
    
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        """Get client information."""
        return self._clients.get(client_id)
    
    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        """Register a new OAuth client."""
        self._clients[client_info.client_id] = client_info
    
    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        """Handle authorization request - redirect to Drupal OAuth."""
        # Generate auth code
        import secrets
        auth_code = secrets.token_urlsafe(32)
        self._auth_codes[auth_code] = {
            "client_id": client.client_id,
            "redirect_uri": params.redirect_uri,
            "scopes": params.scopes,
            "code_challenge": params.code_challenge,
        }
        
        # Redirect back to client with auth code
        return f"{params.redirect_uri}?code={auth_code}"
    
    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCodeT,
    ) -> OAuthToken:
        """Exchange authorization code for access token."""
        auth_code_str = str(authorization_code)
        if auth_code_str not in self._auth_codes:
            raise ValueError("Invalid authorization code")
        
        code_data = self._auth_codes.pop(auth_code_str)
        
        # Generate tokens
        import secrets
        import time
        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32)
        expires_at = time.time() + 3600  # 1 hour
        
        token_data = {
            "token": access_token,
            "client_id": client.client_id,
            "scopes": code_data["scopes"],
            "expires_at": expires_at,
        }
        self._access_tokens[access_token] = token_data
        self._refresh_tokens[refresh_token] = {
            "client_id": client.client_id,
            "scopes": code_data["scopes"],
        }
        
        return OAuthToken(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="Bearer",
            expires_in=3600,
            scope=" ".join(code_data["scopes"]),
        )
    
    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshTokenT,
        scopes: list[str],
    ) -> OAuthToken:
        """Exchange refresh token for new access token."""
        refresh_token_str = str(refresh_token)
        if refresh_token_str not in self._refresh_tokens:
            raise ValueError("Invalid refresh token")
        
        token_data = self._refresh_tokens[refresh_token_str]
        
        import secrets
        import time
        new_access_token = secrets.token_urlsafe(32)
        new_refresh_token = secrets.token_urlsafe(32)
        expires_at = time.time() + 3600
        
        new_token_data = {
            "token": new_access_token,
            "client_id": client.client_id,
            "scopes": scopes,
            "expires_at": expires_at,
        }
        self._access_tokens[new_access_token] = new_token_data
        self._refresh_tokens[new_refresh_token] = {
            "client_id": client.client_id,
            "scopes": scopes,
        }
        del self._refresh_tokens[refresh_token_str]
        
        return OAuthToken(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="Bearer",
            expires_in=3600,
            scope=" ".join(scopes),
        )
    
    async def revoke_token(self, token: AccessToken | RefreshTokenT) -> None:
        """Revoke an access or refresh token."""
        token_str = str(token)
        self._access_tokens.pop(token_str, None)
        self._refresh_tokens.pop(token_str, None)
