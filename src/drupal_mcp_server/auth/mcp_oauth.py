"""In-process OAuth 2.1 authorization server for the MCP HTTP transport.

Codes and access tokens are issued and validated from memory; nothing is
delegated to Drupal (see ADR 0005). The Drupal OAuth credentials handed
in via the constructor belong to the outbound client-credentials leg and
are stored for follow-up wiring only.
"""

from typing import Any, cast

from fastmcp.server.auth import AccessToken as FastMCPAccessToken
from fastmcp.server.auth import OAuthProvider
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationCodeT,
    AuthorizationParams,
    RefreshToken,
    RefreshTokenT,
)
from mcp.server.auth.settings import ClientRegistrationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl


class DrupalOAuthProvider(OAuthProvider):
    """In-process OAuth 2.1 provider with per-session scopes.

    Issues its own codes and tokens (no Drupal delegation — see ADR 0005),
    so the flow verifies that the caller speaks OAuth, not who the user is.
    """
    
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
            # Without registration the client registry can never be
            # populated, /token rejects every client as invalid_client,
            # and no MCP client can obtain a token over the wire. Dynamic
            # client registration is what the MCP spec expects of a remote
            # authorization server; it proves client-ness, not identity.
            client_registration_options=ClientRegistrationOptions(enabled=True),
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
        """Load and validate an access token.

        The token has to be returned as an `AccessToken`, not as the dict it
        was stored in. FastMCP reads `.scopes` and `.client_id` off the result
        to decide whether a request is allowed, and a dict answers every one of
        those with `AttributeError` -- so a perfectly good token was rejected as
        harshly as a forged one, and the only OAuth behaviour ever observed was
        the fail-closed side. That also makes this the constructor of last
        resort for the stored fields, which is why `expires_at` is stored as an
        int: `AccessToken.expires_at` is one, and a float fails its validation.
        """
        token_data = self._access_tokens.get(token)
        if token_data is None:
            return None
        import time

        if token_data.get("expires_at", 0) <= time.time():
            return None
        return FastMCPAccessToken(
            token=str(token_data.get("token", token)),
            client_id=str(token_data.get("client_id") or ""),
            scopes=list(token_data.get("scopes") or []),
            expires_at=int(token_data.get("expires_at", 0)),
        )
    
    async def load_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: str,
    ) -> AuthorizationCodeT | None:
        """Load an authorization code as the model the SDK validates.

        The token handler reads `.client_id`, `.expires_at`,
        `.redirect_uri` and `.code_challenge` off the result to reject
        foreign, expired, redirected and non-PKCE exchanges. Handing back
        the dict the code was stored in raised `AttributeError: 'dict'
        object has no attribute 'client_id'` and turned every /token
        request into a 500 — the same failure shape as the
        load_access_token bug above: what the SDK is handed must be the
        model, not the storage.
        """
        code_data = self._auth_codes.get(str(authorization_code))
        if code_data is None:
            return None
        return cast(
            "AuthorizationCodeT",
            AuthorizationCode(
                code=str(code_data.get("code") or authorization_code),
                scopes=list(code_data.get("scopes") or []),
                expires_at=float(code_data.get("expires_at") or 0),
                client_id=str(code_data.get("client_id") or ""),
                code_challenge=str(code_data.get("code_challenge") or ""),
                redirect_uri=cast(
                    "AnyUrl",
                    code_data.get("redirect_uri") or "http://127.0.0.1/callback",
                ),
                redirect_uri_provided_explicitly=bool(
                    code_data.get("redirect_uri_provided_explicitly")
                ),
            ),
        )
    
    async def load_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: str,
    ) -> RefreshTokenT | None:
        """Load a refresh token as the model the SDK validates.

        Same contract as load_authorization_code: the handler reads
        `.client_id` and `.scopes` off the result, and the stored dict
        answered with AttributeError.
        """
        token_data = self._refresh_tokens.get(str(refresh_token))
        if token_data is None:
            return None
        return cast(
            "RefreshTokenT",
            RefreshToken(
                token=str(refresh_token),
                client_id=str(token_data.get("client_id") or ""),
                scopes=list(token_data.get("scopes") or []),
            ),
        )
    
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        """Get client information."""
        return self._clients.get(client_id)
    
    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        """Register a new OAuth client."""
        self._clients[client_info.client_id] = client_info
    
    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        """Issue an authorization code in-process.

        No user identity is verified here — the missing Drupal-side
        delegation is recorded in ADR 0005 and is exactly what a future
        proxied flow would replace.
        """
        # Generate auth code
        import secrets
        import time
        auth_code = secrets.token_urlsafe(32)
        self._auth_codes[auth_code] = {
            "code": auth_code,
            "client_id": client.client_id,
            "redirect_uri": params.redirect_uri,
            "scopes": list(params.scopes or []),
            "code_challenge": params.code_challenge,
            # RFC 6749 §10.5: codes must expire. The SDK's token handler
            # enforces the deadline off the loaded model.
            "expires_at": time.time() + 600,
            "redirect_uri_provided_explicitly": bool(
                getattr(params, "redirect_uri_provided_explicitly", False)
            ),
        }
        
        # Redirect back to client with auth code
        return f"{params.redirect_uri}?code={auth_code}"
    
    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCodeT,
    ) -> OAuthToken:
        """Exchange authorization code for access token."""
        # The SDK's token handler hands back the loaded model; the unit
        # tests hand the raw string. Both resolve to the stored code.
        auth_code_str = str(getattr(authorization_code, "code", authorization_code))
        if auth_code_str not in self._auth_codes:
            raise ValueError("Invalid authorization code")
        
        code_data = self._auth_codes.pop(auth_code_str)
        
        # Generate tokens
        import secrets
        import time
        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32)
        expires_at = int(time.time()) + 3600  # 1 hour
        
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
        # Same as exchange_authorization_code: the SDK passes the loaded
        # RefreshToken model, the unit tests the raw string.
        refresh_token_str = str(getattr(refresh_token, "token", refresh_token))
        if refresh_token_str not in self._refresh_tokens:
            raise ValueError("Invalid refresh token")
        
        # Indexed for its KeyError side effect: it rejects unknown tokens.
        _token_data = self._refresh_tokens[refresh_token_str]
        
        import secrets
        import time
        new_access_token = secrets.token_urlsafe(32)
        new_refresh_token = secrets.token_urlsafe(32)
        expires_at = int(time.time()) + 3600
        
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
