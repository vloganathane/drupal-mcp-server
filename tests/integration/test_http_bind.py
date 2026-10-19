"""The real-socket path: bind a port, run OAuth discovery, demand nothing.

Every other HTTP test either fakes `FastMCP.run()` (wiring only) or drives
the app in-process on an `ASGITransport` (middleware only). Nobody had ever
actually started uvicorn, so the launch path — guard, provider, discovery
routes, challenge — was unobserved until this test. It runs the installed
console script exactly the way an operator would.
"""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_a_real_socket_binds_with_oauth_and_refuses_the_unauthenticated(
    tmp_path: Path,
) -> None:
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

        metadata = httpx.get(
            f"{base}/.well-known/oauth-authorization-server", timeout=5.0
        ).json()
        assert "authorization_endpoint" in metadata, metadata
        assert metadata["authorization_endpoint"].endswith("/authorize")
        assert metadata["token_endpoint"].endswith("/token")

        initialize = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "probe", "version": "1"},
            },
        }
        refused = httpx.post(f"{base}/mcp", json=initialize, timeout=5.0)
        assert refused.status_code == 401, "an unauthenticated client got through"
        challenge = refused.headers.get("www-authenticate", "")
        assert challenge.startswith("Bearer"), challenge
        # The production scope requirement must be what the socket advertises.
        assert 'scope="drupal:read drupal:write"' in challenge, challenge

        # A client that follows the challenge must be able to resolve it.
        assert 'resource_metadata="' in challenge, challenge
        resource_metadata = challenge.split('resource_metadata="')[1].split('"')[0]
        assert httpx.get(resource_metadata, timeout=5.0).status_code == 200
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
