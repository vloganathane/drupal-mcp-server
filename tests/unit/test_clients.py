"""Unit tests for Drupal clients."""

import json
from typing import Any

import httpx
import pytest

from drupal_mcp_server.clients import JSONAPIClient


class FakeSettings:
    """Minimal settings stand-in for client construction."""

    DRUPAL_BASE_URL = "https://example.test"
    DRUPAL_JSONAPI_PATH = "/jsonapi"
    DRUPAL_GRAPHQL_PATH = "/graphql"


class FakeResponse:
    def __init__(self, status_code: int = 200, content: bytes = b'{"data": []}'):
        self.status_code = status_code
        self.content = content

    def json(self) -> Any:
        return json.loads(self.content or b"{}")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)


def _capture(monkeypatch: pytest.MonkeyPatch, resp: FakeResponse) -> dict[str, Any]:
    """Patch httpx at the transport boundary so real client code runs end to end."""
    seen: dict[str, Any] = {}

    async def fake_request(self: Any, url: str, **kwargs: Any) -> FakeResponse:
        seen["url"] = url
        seen["params"] = kwargs.get("params")
        seen["headers"] = kwargs.get("headers")
        seen["json"] = kwargs.get("json")
        return resp

    for verb in ("get", "post", "patch", "delete"):
        monkeypatch.setattr(httpx.AsyncClient, verb, fake_request, raising=True)
    return seen


def test_jsonapi_client_exists():
    from drupal_mcp_server.clients import JSONAPIClient

    assert JSONAPIClient is not None


@pytest.mark.asyncio
async def test_get_by_id_accepts_params(monkeypatch: pytest.MonkeyPatch):
    """get_by_id must accept params, or every *_get tool raises TypeError."""
    client = JSONAPIClient(FakeSettings())
    seen = _capture(monkeypatch, FakeResponse())

    await client.get_by_id("node", "abc", params={"include": "uid"})

    assert seen["url"] == "https://example.test/jsonapi/node/abc"
    assert seen["params"] == {"include": "uid"}


@pytest.mark.asyncio
async def test_get_by_id_without_params(monkeypatch: pytest.MonkeyPatch):
    client = JSONAPIClient(FakeSettings())
    seen = _capture(monkeypatch, FakeResponse())

    await client.get_by_id("node", "abc")

    assert seen["params"] is None


@pytest.mark.asyncio
async def test_delete_tolerates_204_no_content(monkeypatch: pytest.MonkeyPatch):
    """Drupal DELETE returns 204 with an empty body; parsing it as JSON must not raise."""
    client = JSONAPIClient(FakeSettings())
    _capture(monkeypatch, FakeResponse(status_code=204, content=b""))

    result = await client.delete_resource("node", "abc")

    assert result["deleted"] is True


@pytest.mark.asyncio
async def test_headers_include_auth(monkeypatch: pytest.MonkeyPatch):
    """AuthManager.get_headers is sync; awaiting it would drop all credentials."""

    class SyncAuth:
        def get_headers(self) -> dict[str, str]:
            return {"Authorization": "Basic abc"}

    client = JSONAPIClient(FakeSettings(), SyncAuth())
    seen = _capture(monkeypatch, FakeResponse())

    await client.get_resource("node--article")

    assert seen["headers"]["Authorization"] == "Basic abc"


def test_auth_manager_get_headers_is_sync():
    """A coroutine here silently breaks every HTTP call with 'not iterable'."""
    import inspect

    from drupal_mcp_server.auth import AuthManager

    assert not inspect.iscoroutinefunction(AuthManager.get_headers)


def test_base_client_timeout_is_set():
    """Every outbound request must carry a timeout."""
    client = JSONAPIClient(FakeSettings())
    assert isinstance(client._timeout, int | float)
    assert client._timeout > 0
