"""ADR 0005's delegation option, built: proxy issuance + token validation.

The default posture stays the in-process authorization server. This
covers the opt-in networked posture the ADR recommends once a multi-user
deployment needs Drupal-side identity: MCP clients keep discovery/DCR/
PKCE against us, authorize/token requests are forwarded to Drupal's
simple_oauth server, and every presented token is validated per request
— locally via JWKS (no hop) or by RFC 7662 introspection (hop per cold
token, cached).

Offline proof: endpoint derivation is pure; JWT validation is proven
against a locally generated RSA keypair — signature, expiry, audience
and scope failures all answer None; introspection is proven against a
stub RFC 7662 endpoint including its cache. The one leg this cannot
cover is the live simple_oauth round trip — the test site has no
simple_oauth module, recorded as a live gap alongside the outbound
client-credentials leg.
"""

import asyncio
import base64
import types

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from fastmcp.server.auth.oauth_proxy import OAuthProxy
from fastmcp.server.auth.providers.introspection import IntrospectionTokenVerifier
from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair

from drupal_mcp_server.auth.delegation import (
    delegate_provider,
    endpoints,
    public_base_url,
    token_verifier,
)


def _settings(**overrides):
    """A settings stub with the delegate-mode fields at their defaults."""
    base = dict(
        DRUPAL_OAUTH_CLIENT_ID="mcp-client",
        DRUPAL_OAUTH_CLIENT_SECRET="s3cret",
        DRUPAL_OAUTH_TOKEN_URL="https://site.example/oauth/token",
        DRUPAL_OAUTH_AUTH_ENDPOINT=None,
        DRUPAL_OAUTH_JWKS_URI=None,
        DRUPAL_OAUTH_INTROSPECTION_URL=None,
        DRUPAL_OAUTH_AUDIENCE=None,
        DRUPAL_OAUTH_REQUIRED_SCOPES="",
        MCP_BASE_URL=None,
        MCP_HOST="127.0.0.1",
        MCP_PORT=8000,
    )
    base.update(overrides)
    return types.SimpleNamespace(**base)


# --- endpoint derivation ----------------------------------------------------


def test_default_endpoints_follow_the_simple_oauth_convention() -> None:
    derived = endpoints(_settings())
    assert derived["authorize"] == "https://site.example/oauth/authorize"
    assert derived["token"] == "https://site.example/oauth/token"
    assert derived["validate"] == "https://site.example/oauth/jwks"


def test_explicit_endpoints_override_the_convention() -> None:
    derived = endpoints(
        _settings(
            DRUPAL_OAUTH_AUTH_ENDPOINT="https://as.example/authorize",
            DRUPAL_OAUTH_JWKS_URI="https://as.example/.well-known/jwks.json",
        )
    )
    assert derived["authorize"] == "https://as.example/authorize"
    assert derived["validate"] == "https://as.example/.well-known/jwks.json"
    assert derived["token"] == "https://site.example/oauth/token"


def test_introspection_endpoint_wins_over_jwks_when_configured() -> None:
    derived = endpoints(
        _settings(DRUPAL_OAUTH_INTROSPECTION_URL="https://site.example/oauth/introspect")
    )
    assert derived["validate"] == "https://site.example/oauth/introspect"


def test_unconventional_token_url_fails_loudly_without_explicit_endpoints() -> None:
    settings = _settings(DRUPAL_OAUTH_TOKEN_URL="https://site.example/token-endpoint")
    with pytest.raises(SystemExit) as excinfo:
        endpoints(settings)
    message = str(excinfo.value)
    assert "DRUPAL_OAUTH_AUTH_ENDPOINT" in message
    assert "DRUPAL_OAUTH_TOKEN_URL" in message
    # The same setting also drives JWKS and introspection defaults.
    assert "DRUPAL_OAUTH_JWKS_URI" in message


def test_required_scopes_parse_from_csv() -> None:
    # The verifier normalizes "no minimum" to an empty list.
    assert token_verifier(_settings()).required_scopes == []
    verifier = token_verifier(
        _settings(DRUPAL_OAUTH_REQUIRED_SCOPES="drupal:read, drupal:write")
    )
    assert verifier.required_scopes == ["drupal:read", "drupal:write"]


def test_validation_mode_follows_the_introspection_switch() -> None:
    assert isinstance(token_verifier(_settings()), JWTVerifier)
    verifier = token_verifier(
        _settings(DRUPAL_OAUTH_INTROSPECTION_URL="https://site.example/oauth/introspect")
    )
    assert isinstance(verifier, IntrospectionTokenVerifier)


# --- the built provider -----------------------------------------------------


def test_delegate_provider_carries_the_upstream_credentials() -> None:
    provider = delegate_provider(_settings())
    assert isinstance(provider, OAuthProxy)
    assert provider._upstream_client_id == "mcp-client"
    assert isinstance(provider._token_validator, JWTVerifier)
    assert provider._token_validator.jwks_uri == "https://site.example/oauth/jwks"


def test_delegate_refuses_to_build_without_upstream_credentials() -> None:
    settings = _settings(DRUPAL_OAUTH_CLIENT_SECRET=None, DRUPAL_OAUTH_TOKEN_URL=None)
    with pytest.raises(SystemExit) as excinfo:
        delegate_provider(settings)
    message = str(excinfo.value)
    assert "DRUPAL_OAUTH_CLIENT_SECRET" in message
    assert "DRUPAL_OAUTH_TOKEN_URL" in message
    assert "simple_oauth" in message


# --- local JWT validation ---------------------------------------------------


def test_a_locally_signed_token_verifies_and_the_altered_ones_do_not() -> None:
    pair = RSAKeyPair.generate()
    verifier = JWTVerifier(
        public_key=pair.public_key,
        audience="mcp-resource",
        required_scopes=["drupal:read"],
    )
    good = pair.create_token(
        subject="alice",
        issuer="https://site.example",
        audience="mcp-resource",
        scopes=["drupal:read", "drupal:write"],
        expires_in_seconds=600,
    )
    access = asyncio.run(verifier.verify_token(good))
    assert access is not None
    assert access.client_id == "alice"
    assert access.scopes == ["drupal:read", "drupal:write"]

    assert asyncio.run(verifier.verify_token(good[:-4] + "AAAA")) is None

    expired = pair.create_token(
        subject="alice",
        issuer="https://site.example",
        audience="mcp-resource",
        scopes=["drupal:read"],
        expires_in_seconds=-60,
    )
    assert asyncio.run(verifier.verify_token(expired)) is None

    wrong_audience = pair.create_token(
        subject="alice",
        issuer="https://site.example",
        audience="someone-else",
        scopes=["drupal:read"],
        expires_in_seconds=600,
    )
    assert asyncio.run(verifier.verify_token(wrong_audience)) is None

    missing_scope = pair.create_token(
        subject="alice",
        issuer="https://site.example",
        audience="mcp-resource",
        scopes=["drupal:other"],
        expires_in_seconds=600,
    )
    assert asyncio.run(verifier.verify_token(missing_scope)) is None


def test_jwks_uri_verification_over_the_wire() -> None:
    """The default posture fetches keys from the upstream JWKS endpoint."""
    pair = RSAKeyPair.generate()
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"keys": [_jwk_for(pair, "site-key")]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    verifier = JWTVerifier(
        jwks_uri="https://site.example/oauth/jwks",
        audience="mcp-resource",
        http_client=client,
    )
    token = pair.create_token(
        subject="alice",
        issuer="https://site.example",
        audience="mcp-resource",
        scopes=["drupal:read"],
        expires_in_seconds=600,
        kid="site-key",
    )
    access = asyncio.run(verifier.verify_token(token))
    assert access is not None and access.client_id == "alice"
    assert calls == ["/oauth/jwks"], "keys are fetched once and cached"


def _jwk_for(pair: RSAKeyPair, kid: str) -> dict:
    """A public JWK for a generated key, in the shape JWKS serves."""
    public = serialization.load_pem_public_key(pair.public_key.encode())
    numbers = public.public_numbers()  # type: ignore[union-attr]
    n = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")
    return {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
        "n": base64.urlsafe_b64encode(n).rstrip(b"=").decode(),
        "e": "AQAB",
    }


# --- introspection validation ----------------------------------------------


def test_introspection_asks_the_upstream_once_and_caches() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(
            200, json={"active": True, "scope": "drupal:read", "client_id": "alice"}
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    verifier = IntrospectionTokenVerifier(
        introspection_url="https://site.example/oauth/token/introspect",
        client_id="mcp-client",
        client_secret="s3cret",
        http_client=client,
        cache_ttl_seconds=60,
    )
    access = asyncio.run(verifier.verify_token("opaque-token"))
    assert access is not None
    assert access.client_id == "alice"
    assert asyncio.run(verifier.verify_token("opaque-token")) is not None
    assert calls == ["/oauth/token/introspect"], "second use must hit the cache"

    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"active": False})

    refused = IntrospectionTokenVerifier(
        introspection_url="https://site.example/oauth/token/introspect",
        client_id="mcp-client",
        client_secret="s3cret",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(refuse)),
    )
    assert asyncio.run(refused.verify_token("revoked-token")) is None


# --- public base URL --------------------------------------------------------


def test_public_base_url_defaults_to_host_port_and_honors_overrides() -> None:
    assert public_base_url(_settings()) == "http://127.0.0.1:8000"
    # 0.0.0.0 is a bind address, not a redirect target.
    assert public_base_url(_settings(MCP_HOST="0.0.0.0")) == "http://127.0.0.1:8000"
    assert (
        public_base_url(_settings(MCP_BASE_URL="https://mcp.example"))
        == "https://mcp.example"
    )


# --- server wiring ----------------------------------------------------------


def test_server_wiring_picks_the_provider_by_the_switch() -> None:
    from drupal_mcp_server.server import _oauth_provider_for

    class _Manager:
        def get_mcp_oauth_provider(self, settings):
            return "in-process-provider"

    def merged(flags: dict):
        values = vars(_settings())
        values.update(flags)
        return types.SimpleNamespace(**values)

    delegated = _oauth_provider_for(merged({"DRUPAL_OAUTH_DELEGATE": True}), _Manager())
    assert isinstance(delegated, OAuthProxy)
    assert (
        _oauth_provider_for(merged({"DRUPAL_OAUTH_DELEGATE": False}), _Manager())
        == "in-process-provider"
    )
