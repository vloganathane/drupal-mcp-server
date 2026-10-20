"""Proxy delegation to Drupal's simple_oauth server (ADR 0005's networked mode).

The served default is the in-process authorization server: nothing is
reachable, nothing is delegated, and a token proves the caller speaks
OAuth, not who the user is. When a multi-user deployment needs
Drupal-side identity, this module builds the delegation the ADR
recommends: MCP clients keep standard discovery/DCR/PKCE against us,
while authorize/token requests are forwarded to Drupal's simple_oauth
authorization server, and every presented token is validated on each
request — locally via JWKS (no per-request hop) or by RFC 7662
introspection (a hop per cold token, cached).

Endpoint convention: simple_oauth serves everything under one prefix,
so the token URL that already does the outbound client-credentials job
(``DRUPAL_OAUTH_TOKEN_URL``) also pins the rest —
``…/oauth/token`` implies ``…/oauth/authorize`` and ``…/oauth/jwks``.
Each has an explicit override, and a token URL that does not end in
``/token`` fails at startup rather than guessing.
"""

from typing import Any

from fastmcp.server.auth import TokenVerifier
from fastmcp.server.auth.oauth_proxy import OAuthProxy
from fastmcp.server.auth.providers.introspection import IntrospectionTokenVerifier
from fastmcp.server.auth.providers.jwt import JWTVerifier


def _derive(token_url: str, tail: str, explicit: str | None) -> str:
    """An explicit endpoint wins; else derive it from the token URL."""
    if explicit:
        return explicit
    if not token_url.endswith("/token"):
        raise SystemExit(
            f"DRUPAL_OAUTH_TOKEN_URL={token_url!r} does not end in /token, so "
            "the authorize/JWKS endpoints cannot follow the simple_oauth "
            "convention. Set DRUPAL_OAUTH_AUTH_ENDPOINT and "
            "DRUPAL_OAUTH_JWKS_URI explicitly (or point TOKEN_URL at the "
            "server's /oauth/token)."
        )
    return token_url[: -len("/token")] + tail


def endpoints(settings: Any) -> dict[str, str]:
    """The upstream endpoints delegation uses, resolved or derived."""
    token_url = str(settings.DRUPAL_OAUTH_TOKEN_URL or "")
    validate = settings.DRUPAL_OAUTH_INTROSPECTION_URL or _derive(
        token_url, "/jwks", settings.DRUPAL_OAUTH_JWKS_URI
    )
    return {
        "authorize": _derive(token_url, "/authorize", settings.DRUPAL_OAUTH_AUTH_ENDPOINT),
        "token": token_url,
        "validate": validate,
    }


def required_scopes(settings: Any) -> list[str] | None:
    """The minimum scopes a delegated token must carry.

    Empty means no MCP-side minimum: the token validated, and tool
    authorization is whatever Drupal put in it. Delegate mode starts
    here because our drupal:* scopes are an in-process invention; a
    deployment that maps scopes in Drupal sets this to match.
    """
    raw = str(settings.DRUPAL_OAUTH_REQUIRED_SCOPES or "").strip()
    scopes = [scope.strip() for scope in raw.split(",") if scope.strip()]
    return scopes or None


def token_verifier(settings: Any) -> TokenVerifier:
    """How each presented token is checked, per request."""
    resolved = endpoints(settings)
    scopes = required_scopes(settings)
    if settings.DRUPAL_OAUTH_INTROSPECTION_URL:
        return IntrospectionTokenVerifier(
            introspection_url=resolved["validate"],
            client_id=settings.DRUPAL_OAUTH_CLIENT_ID,
            client_secret=settings.DRUPAL_OAUTH_CLIENT_SECRET,
            required_scopes=scopes,
            audience=settings.DRUPAL_OAUTH_AUDIENCE,
        )
    return JWTVerifier(
        jwks_uri=resolved["validate"],
        audience=settings.DRUPAL_OAUTH_AUDIENCE,
        required_scopes=scopes,
    )


def public_base_url(settings: Any) -> str:
    """The URL MCP clients reach this server on, for OAuth redirects."""
    if settings.MCP_BASE_URL:
        return str(settings.MCP_BASE_URL)
    # 0.0.0.0 is a bind address, not a redirect target.
    host = "127.0.0.1" if settings.MCP_HOST == "0.0.0.0" else settings.MCP_HOST
    return f"http://{host}:{settings.MCP_PORT}"


def delegate_provider(settings: Any) -> OAuthProxy:
    """Build the delegating provider, or refuse loudly at startup."""
    missing = [
        name
        for name, value in (
            ("DRUPAL_OAUTH_CLIENT_ID", settings.DRUPAL_OAUTH_CLIENT_ID),
            ("DRUPAL_OAUTH_CLIENT_SECRET", settings.DRUPAL_OAUTH_CLIENT_SECRET),
            ("DRUPAL_OAUTH_TOKEN_URL", settings.DRUPAL_OAUTH_TOKEN_URL),
        )
        if not value
    ]
    if missing:
        raise SystemExit(
            "DRUPAL_OAUTH_DELEGATE=1 forwards MCP authorize/token requests to "
            "Drupal's simple_oauth server, which needs the upstream OAuth "
            f"client registered there and these set: {', '.join(missing)}. "
            "Configure them, or unset DRUPAL_OAUTH_DELEGATE to keep the "
            "default in-process authorization server."
        )
    resolved = endpoints(settings)
    return OAuthProxy(
        upstream_authorization_endpoint=resolved["authorize"],
        upstream_token_endpoint=resolved["token"],
        upstream_client_id=settings.DRUPAL_OAUTH_CLIENT_ID,
        upstream_client_secret=settings.DRUPAL_OAUTH_CLIENT_SECRET,
        token_verifier=token_verifier(settings),
        base_url=public_base_url(settings),
        valid_scopes=required_scopes(settings),
    )
