"""ADR 0005's delegation over real sockets, end to end.

The unit suite proves the delegating provider builds and that token
validation answers None for bad tokens; test_http_bind proves the
default posture over a wire. The leg neither covered is delegate mode
in production shape: the installed console script started with
DRUPAL_OAUTH_DELEGATE=1, an MCP client walking discovery → DCR →
authorize → consent → upstream redirect → both code exchanges → a
bearer call, with every outbound hop crossing a loopback socket to a
spec-conformant stub standing in for Drupal's simple_oauth
authorize/token/JWKS endpoints.

Honest boundary: the stub is ours. No Drupal with the simple_oauth
module runs in this environment, so what this pins is the proxy
machinery — endpoint derivation, PKCE forwarding, the consent screen
and its binding cookie, the Basic-auth upstream exchange, local
redemption, JWKS validation of the presented token — not Drupal's own
conformance, which remains a live gap.
"""

import asyncio
import base64
import hashlib
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
import pytest
import uvicorn
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from fastmcp.server.auth.providers.jwt import RSAKeyPair
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Route

_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "delegation-probe", "version": "1"},
    },
}

# The upstream OAuth client delegate mode is configured with; the stub
# only exchanges codes for whoever authenticates as this pair, in Basic
# auth, the way simple_oauth's client_secret_basic default does.
_UPSTREAM_CLIENT_ID = "mcp-client"
_UPSTREAM_CLIENT_SECRET = "s3cret"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _int_to_b64url(value: int) -> str:
    size = (value.bit_length() + 7) // 8
    return _b64url(value.to_bytes(size, "big"))


class _StubSimpleOAuth:
    """A spec-conformant authorize/token/JWKS server on a loopback socket.

    Stands in for Drupal's simple_oauth module. Every request it
    receives is recorded so the walk can pin the proxy's production
    posture: its own upstream client_id, a redirect_uri at the derived
    /auth/callback, S256 PKCE, Basic auth on the token exchange — and
    the JWKS endpoint derived from the token URL gets fetched.
    """

    def __init__(self) -> None:
        self.rsa = RSAKeyPair.generate()
        self.base = ""
        self.authorize_requests: list[dict[str, str]] = []
        self.token_requests: list[dict[str, str]] = []
        self.jwks_requests = 0
        self._codes: dict[str, dict[str, str]] = {}

    def app(self) -> Starlette:
        return Starlette(
            routes=[
                Route("/oauth/authorize", self._authorize, methods=["GET"]),
                Route("/oauth/token", self._token, methods=["POST"]),
                Route("/oauth/jwks", self._jwks, methods=["GET"]),
            ]
        )

    def _jwks_document(self) -> dict:
        numbers = load_pem_public_key(self.rsa.public_key.encode()).public_numbers()
        return {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "alg": "RS256",
                    "kid": "stub-simple-oauth",
                    "n": _int_to_b64url(numbers.n),
                    "e": _int_to_b64url(numbers.e),
                }
            ]
        }

    async def _authorize(self, request: Request):
        params = dict(request.query_params)
        self.authorize_requests.append(params)
        redirect_uri = params.get("redirect_uri", "")
        if not redirect_uri:
            return JSONResponse({"error": "invalid_request"}, status_code=400)
        code = secrets.token_urlsafe(16)
        self._codes[code] = {
            "redirect_uri": redirect_uri,
            "challenge": params.get("code_challenge", ""),
        }
        state = params.get("state", "")
        return RedirectResponse(
            f"{redirect_uri}?code={code}&state={state}", status_code=302
        )

    async def _token(self, request: Request):
        form = dict(await request.form())
        record = dict(form)
        record["authorization"] = request.headers.get("authorization", "")
        self.token_requests.append(record)
        expected = "Basic " + base64.b64encode(
            f"{_UPSTREAM_CLIENT_ID}:{_UPSTREAM_CLIENT_SECRET}".encode()
        ).decode()
        if record["authorization"] != expected:
            return JSONResponse({"error": "invalid_client"}, status_code=401)
        if form.get("grant_type") != "authorization_code":
            return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
        entry = self._codes.get(form.get("code", ""))
        if entry is None or form.get("redirect_uri") != entry["redirect_uri"]:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        computed = _b64url(hashlib.sha256(form.get("code_verifier", "").encode()).digest())
        if entry["challenge"] and computed != entry["challenge"]:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        access_token = self.rsa.create_token(
            subject="drupal-user-1",
            issuer=self.base,
            audience="drupal-mcp-test",
            scopes=["mcp:read"],
            kid="stub-simple-oauth",
        )
        return JSONResponse(
            {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": 3600,
                "refresh_token": secrets.token_urlsafe(24),
                "scope": "mcp:read",
            }
        )

    async def _jwks(self, request: Request):
        self.jwks_requests += 1
        return JSONResponse(self._jwks_document())


@contextmanager
def _stub_simple_oauth() -> Iterator[_StubSimpleOAuth]:
    """Run the stub on a real pre-bound socket; yield its recorded state."""
    stub = _StubSimpleOAuth()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    stub.base = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(stub.app(), log_level="warning"))
    thread = threading.Thread(
        target=lambda: asyncio.run(server.serve(sockets=[sock])), daemon=True
    )
    thread.start()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{stub.base}/oauth/jwks", timeout=1.0).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.05)
    else:
        pytest.fail("stub authorization server never answered on its socket")
    try:
        yield stub
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@contextmanager
def _delegating_server(stub_base: str, tmp_path: Path) -> Iterator[str]:
    """Launch the installed console script in delegate posture.

    The environment sets only what delegation needs: the switch, the
    upstream client, the token URL, the audience and the scope
    minimum. Endpoints stay unset on purpose — authorize and JWKS
    must arrive at the stub by the /oauth/token convention, which is
    what the recorded requests then prove.
    """
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    script = Path(sys.executable).with_name("drupal-mcp")
    assert script.exists(), f"console script missing at {script}"

    env = os.environ.copy()
    # Booleans/optionals: must be unset, not blank — pydantic rejects "".
    for key in (
        "MCP_ALLOW_INSECURE_HTTP",
        "MCP_READ_ONLY",
        "MCP_RATE_LIMIT",
        "DRUPAL_OAUTH_AUTH_ENDPOINT",
        "DRUPAL_OAUTH_JWKS_URI",
        "DRUPAL_OAUTH_INTROSPECTION_URL",
    ):
        env.pop(key, None)
    env.update(
        {
            "MCP_TRANSPORT": "http",
            "MCP_HOST": "127.0.0.1",
            "MCP_PORT": str(port),
            "MCP_BASE_URL": base,
            "MCP_LOG_LEVEL": "WARNING",
            "DRUPAL_OAUTH_DELEGATE": "1",
            "DRUPAL_OAUTH_CLIENT_ID": _UPSTREAM_CLIENT_ID,
            "DRUPAL_OAUTH_CLIENT_SECRET": _UPSTREAM_CLIENT_SECRET,
            "DRUPAL_OAUTH_TOKEN_URL": f"{stub_base}/oauth/token",
            "DRUPAL_OAUTH_AUDIENCE": "drupal-mcp-test",
            "DRUPAL_OAUTH_REQUIRED_SCOPES": "mcp:read",
            # Neutralize every other leg so startup cannot reach a network.
            "DRUPAL_USERNAME": "",
            "DRUPAL_PASSWORD": "",
            "DRUPAL_API_TOKEN": "",
            "DRUPAL_BASE_URL": "http://127.0.0.1:1",
            "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost",
            # Proxy storage lands in the test's tmp, not the developer's home.
            "FASTMCP_HOME": str(tmp_path),
        }
    )

    proc = subprocess.Popen(
        [str(script)],
        env=env,
        # No `.env` next to the process: settings come from this env only.
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.monotonic() + 30
        status = 0
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                output = proc.stdout.read() if proc.stdout else ""
                pytest.fail(
                    f"server exited with {proc.returncode} before binding:\n{output}"
                )
            try:
                status = httpx.get(
                    f"{base}/.well-known/oauth-authorization-server", timeout=2.0
                ).status_code
            except httpx.HTTPError:
                status = 0
            if status == 200:
                break
            time.sleep(0.25)
        assert status == 200, "delegating server never answered discovery on its socket"
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def test_delegate_mode_walks_discovery_to_a_bearer_call_over_real_sockets(
    tmp_path: Path,
) -> None:
    """The full delegated round trip, every hop a real socket.

    Delegation is the posture where MCP tokens mean Drupal identity,
    and until now only its parts were tested: the provider builds, bad
    tokens answer None. Here the production entrypoint runs it: a
    client registers, approves the consent screen, crosses the stub's
    authorize endpoint, exchanges both codes, and calls the MCP
    endpoint with the delegated bearer — with the 401s that must
    surround it.
    """
    with _stub_simple_oauth() as stub, _delegating_server(
        stub.base, tmp_path
    ) as base:
        with httpx.Client(follow_redirects=False, timeout=10.0) as client:
            metadata = client.get(
                f"{base}/.well-known/oauth-authorization-server"
            ).json()
            assert metadata["issuer"].rstrip("/") == base, metadata
            assert metadata["authorization_endpoint"] == f"{base}/authorize", metadata
            assert metadata["token_endpoint"] == f"{base}/token", metadata
            assert "registration_endpoint" in metadata, metadata

            redirect_uri = f"{base}/cb"
            registration = client.post(
                f"{base}/register",
                json={
                    "redirect_uris": [redirect_uri],
                    "client_name": "delegation-walk-probe",
                    "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"],
                    "token_endpoint_auth_method": "none",
                    "scope": "mcp:read",
                },
            )
            assert registration.status_code in (200, 201), registration.text
            client_id = registration.json()["client_id"]

            verifier = _b64url(secrets.token_bytes(48))
            challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
            authorize = client.get(
                f"{base}/authorize",
                params={
                    "response_type": "code",
                    "client_id": client_id,
                    "redirect_uri": redirect_uri,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                    "state": "walk-state",
                    "scope": "mcp:read",
                },
            )
            assert authorize.status_code in (302, 303), authorize.text
            consent_target = urljoin(base, authorize.headers.get("location", ""))
            assert urlparse(consent_target).path == "/consent", consent_target
            txn_id = parse_qs(urlparse(consent_target).query)["txn_id"][0]

            # The default posture shows the consent screen every time.
            page = client.get(consent_target)
            assert page.status_code == 200, page.text
            match = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
            assert match, page.text[:500]

            approved = client.post(
                urljoin(base, "/consent"),
                data={
                    "txn_id": txn_id,
                    "csrf_token": match.group(1),
                    "submit": "true",
                    "action": "approve",
                },
            )
            assert approved.status_code in (302, 303), approved.text
            upstream = urljoin(base, approved.headers.get("location", ""))
            assert urlparse(upstream).netloc == urlparse(stub.base).netloc, upstream

            # The upstream redirect pins the production posture: the
            # proxy's own client, the /auth/callback derived from the
            # token URL, the transaction as state, its own PKCE leg.
            upstream_query = parse_qs(urlparse(upstream).query)
            assert upstream_query["client_id"] == [_UPSTREAM_CLIENT_ID], upstream
            assert upstream_query["redirect_uri"] == [f"{base}/auth/callback"], upstream
            assert upstream_query["state"] == [txn_id], upstream
            assert upstream_query["code_challenge_method"] == ["S256"], upstream
            assert "code_challenge" in upstream_query, upstream
            assert "mcp:read" in upstream_query.get("scope", [""])[0], upstream

            # The IdP approves; the browser returns to our callback,
            # which performs the upstream token exchange on this
            # request — Basic auth and PKCE, over the stub's socket.
            upstream_authorized = client.get(upstream)
            assert upstream_authorized.status_code in (302, 303), upstream_authorized.text
            assert len(stub.authorize_requests) == 1, stub.authorize_requests
            assert (
                stub.authorize_requests[0]["redirect_uri"] == f"{base}/auth/callback"
            ), stub.authorize_requests
            callback_target = urljoin(base, upstream_authorized.headers.get("location", ""))
            assert urlparse(callback_target).path == "/auth/callback", callback_target

            completed = client.get(callback_target)
            assert completed.status_code in (302, 303), completed.text[:500]
            final = urljoin(base, completed.headers.get("location", ""))
            assert final.startswith(redirect_uri), final
            final_query = parse_qs(urlparse(final).query)
            assert final_query["state"] == ["walk-state"], final
            assert final_query["iss"][0].rstrip("/") == base, final

            # The upstream exchange crossed the stub's socket with the
            # configured client in Basic auth — one authorization_code
            # grant for the proxy, alongside the single startup probe
            # of the outbound client-credentials leg, which reaches
            # the same token URL with the same upstream client.
            exchanges = [
                record
                for record in stub.token_requests
                if record.get("grant_type") == "authorization_code"
            ]
            assert len(exchanges) == 1, stub.token_requests
            exchanged = exchanges[0]
            expected_basic = "Basic " + base64.b64encode(
                f"{_UPSTREAM_CLIENT_ID}:{_UPSTREAM_CLIENT_SECRET}".encode()
            ).decode()
            assert exchanged["authorization"] == expected_basic, exchanged
            assert exchanged["redirect_uri"] == f"{base}/auth/callback", exchanged
            assert "code_verifier" in exchanged, exchanged
            probes = [
                record
                for record in stub.token_requests
                if record.get("grant_type") == "client_credentials"
            ]
            assert len(probes) == 1, stub.token_requests
            assert probes[0]["client_id"] == _UPSTREAM_CLIENT_ID, probes

            # Redeem our own code against our own PKCE challenge.
            exchange = {
                "grant_type": "authorization_code",
                "code": final_query["code"][0],
                "redirect_uri": redirect_uri,
                "code_verifier": verifier,
                "client_id": client_id,
            }
            token = client.post(f"{base}/token", data=exchange)
            assert token.status_code == 200, token.text
            access_token = token.json()["access_token"]
            assert token.json().get("refresh_token"), token.text

            replay = client.post(f"{base}/token", data=exchange)
            assert replay.status_code >= 400, "an authorization code was accepted twice"

            # The MCP endpoint refuses anonymous and forged callers with
            # a challenge a client can actually resolve.
            refused = client.post(f"{base}/mcp", json=_INITIALIZE)
            assert refused.status_code == 401, refused.text
            challenge_header = refused.headers.get("www-authenticate", "")
            assert challenge_header.startswith("Bearer"), challenge_header
            resource_metadata = challenge_header.split('resource_metadata="')[1].split('"')[0]
            assert client.get(resource_metadata).status_code == 200

            forged = client.post(
                f"{base}/mcp",
                json=_INITIALIZE,
                headers={"Authorization": "Bearer not.a.token"},
            )
            assert forged.status_code == 401, forged.text

            # The delegated bearer is accepted: the local token checks
            # out, and the upstream token it maps to validates against
            # the stub's JWKS — signature, audience, scope.
            authorized = client.post(
                f"{base}/mcp",
                json=_INITIALIZE,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert authorized.status_code == 200, authorized.text
            assert "serverInfo" in authorized.text, authorized.text

            # The JWKS endpoint the token URL derived was fetched —
            # the validation hop nobody had ever taken.
            assert stub.jwks_requests >= 1, stub.jwks_requests
