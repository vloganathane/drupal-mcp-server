"""The real-socket path: bind a port, run the OAuth flow, demand nothing.

Every other HTTP test either fakes `FastMCP.run()` (wiring only) or drives
the app in-process on an `ASGITransport` (middleware only). Nobody had
ever actually started uvicorn, so the launch path and the OAuth flow over
the wire were unobserved until these tests. They run the installed
console script exactly the way an operator would.
"""

import base64
import hashlib
import os
import secrets
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "probe", "version": "1"},
    },
}


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@contextmanager
def _bound_oauth_server(tmp_path: Path) -> Iterator[str]:
    """Launch the installed console script on a free port; yield its base URL."""
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    script = Path(sys.executable).with_name("drupal-mcp")
    assert script.exists(), f"console script missing at {script}"

    env = os.environ.copy()
    # A bool field: must be unset, not blank — pydantic rejects "".
    env.pop("MCP_ALLOW_INSECURE_HTTP", None)
    env.update(
        {
            "MCP_TRANSPORT": "http",
            "MCP_HOST": "127.0.0.1",
            "MCP_PORT": str(port),
            "MCP_LOG_LEVEL": "WARNING",
            "DRUPAL_OAUTH_CLIENT_ID": "bind-test",
            # Neutralize every other leg so startup cannot reach a network.
            "DRUPAL_OAUTH_CLIENT_SECRET": "",
            "DRUPAL_OAUTH_TOKEN_URL": "",
            "DRUPAL_USERNAME": "",
            "DRUPAL_PASSWORD": "",
            "DRUPAL_API_TOKEN": "",
            "DRUPAL_BASE_URL": "http://127.0.0.1:1",
            "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost",
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
        assert status == 200, "OAuth discovery never answered on the bound socket"
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def test_a_real_socket_binds_with_oauth_and_refuses_the_unauthenticated(
    tmp_path: Path,
) -> None:
    with _bound_oauth_server(tmp_path) as base:
        metadata = httpx.get(
            f"{base}/.well-known/oauth-authorization-server", timeout=5.0
        ).json()
        assert "authorization_endpoint" in metadata, metadata
        assert metadata["authorization_endpoint"].endswith("/authorize")
        assert metadata["token_endpoint"].endswith("/token")

        refused = httpx.post(f"{base}/mcp", json=_INITIALIZE, timeout=5.0)
        assert refused.status_code == 401, "an unauthenticated client got through"
        challenge = refused.headers.get("www-authenticate", "")
        assert challenge.startswith("Bearer"), challenge
        # The production scope requirement must be what the socket advertises.
        assert 'scope="drupal:read drupal:write"' in challenge, challenge

        # A client that follows the challenge must be able to resolve it.
        assert 'resource_metadata="' in challenge, challenge
        resource_metadata = challenge.split('resource_metadata="')[1].split('"')[0]
        assert httpx.get(resource_metadata, timeout=5.0).status_code == 200


def test_a_client_can_register_authorize_and_call_over_the_socket(
    tmp_path: Path,
) -> None:
    """The full acquisition path, which no test had ever taken.

    Enforcement (401/403/200) had only been proven with tokens minted
    in-process. Over the wire, `/token` authenticates clients against a
    registry that only `/register` can populate — and that endpoint was
    not mounted, so every real client died at `invalid_client`. Walk the
    whole spec flow against a live socket: discover, register, authorize
    with PKCE, exchange, call, replay the code, refresh.
    """
    with _bound_oauth_server(tmp_path) as base:
        metadata = httpx.get(
            f"{base}/.well-known/oauth-authorization-server", timeout=5.0
        ).json()
        assert "registration_endpoint" in metadata, "DCR is not advertised"

        redirect_uri = "https://example.test/callback"
        registration = httpx.post(
            f"{base}/register",
            json={
                "redirect_uris": [redirect_uri],
                "client_name": "socket-journey-probe",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "client_secret_post",
                "scope": "drupal:read drupal:write",
            },
            timeout=5.0,
        )
        assert registration.status_code in (200, 201), registration.text
        client = registration.json()
        client_id = client["client_id"]
        client_secret = client.get("client_secret", "")

        verifier = _b64url(secrets.token_bytes(48))
        challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
        authorize = httpx.get(
            f"{base}/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "probe",
                "scope": "drupal:read drupal:write",
            },
            follow_redirects=False,
            timeout=5.0,
        )
        assert authorize.status_code in (302, 303), authorize.text
        location = authorize.headers.get("location", "")
        assert "code=" in location, location
        code = parse_qs(urlparse(location).query)["code"][0]

        exchange = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
            "code_verifier": verifier,
        }
        token = httpx.post(f"{base}/token", data=exchange, timeout=5.0)
        assert token.status_code == 200, token.text
        access_token = token.json()["access_token"]

        call = httpx.post(
            f"{base}/mcp",
            json=_INITIALIZE,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10.0,
        )
        assert call.status_code == 200, call.text

        replay = httpx.post(f"{base}/token", data=exchange, timeout=5.0)
        assert replay.status_code >= 400, "an authorization code was accepted twice"

        refresh_token = token.json().get("refresh_token")
        assert refresh_token, "no refresh token issued"
        refreshed = httpx.post(
            f"{base}/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=5.0,
        )
        assert refreshed.status_code == 200, refreshed.text
