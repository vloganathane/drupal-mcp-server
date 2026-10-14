"""Unit tests for revision tools.

The old implementation built ``/jsonapi/article/article/10/revisions`` and
passed it to a JSON:API that has never served that path (405).
"""

import json
from typing import Any

import pytest

from drupal_mcp_server.clients import JSONAPIClient
from drupal_mcp_server.tools import revisions


class FakeSettings:
    DRUPAL_BASE_URL = "https://example.test"
    DRUPAL_JSONAPI_PATH = "/jsonapi"
    DRUPAL_GRAPHQL_PATH = "/graphql"
    DRUPAL_VERIFY_SSL = True


class FakeResponse:
    def __init__(self, status_code: int = 200, content: bytes = b"{}"):
        self.status_code = status_code
        self.content = content

    @property
    def text(self) -> str:
        return self.content.decode() if self.content else ""

    def json(self) -> Any:
        return json.loads(self.content or b"{}")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise AssertionError(f"unexpected {self.status_code}")


def _capture(monkeypatch, responder=None) -> list[dict[str, Any]]:
    """Patch httpx at the transport boundary so real client code runs."""
    requests: list[dict[str, Any]] = []

    async def fake_request(self, method, url, **kwargs):
        entry = {"method": method, "url": url, "params": kwargs.get("params"),
                 "json": kwargs.get("json")}
        requests.append(entry)
        if responder is not None:
            return responder(entry)
        return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient.request", fake_request, raising=True)
    return requests


def _register():
    """Return the registered tool callables keyed by name."""

    class FakeMCP:
        def __init__(self):
            self.fns: dict[str, Any] = {}

        def tool(self, *args, **kwargs):
            def decorate(fn):
                self.fns[fn.__name__] = fn
                return fn
            return decorate

    mcp = FakeMCP()
    revisions.register_tools(mcp, jsonapi_client=JSONAPIClient(FakeSettings()))
    return mcp.fns


UUID = "4d9ecad4-49d5-481d-bf4e-8cfe9fde5471"
NODE = {
    "type": "node--article",
    "id": UUID,
    "attributes": {"drupal_internal__nid": 1, "drupal_internal__vid": 7, "title": "Hi"},
}


def _node_responder(revision_attrs: dict[str, Any] | None = None):
    """Answers id-resolution filters, plain reads, and resourceVersion reads."""

    def responder(entry):
        params = entry["params"] or {}
        if any(k.startswith("filter[") for k in params):
            return FakeResponse(content=json.dumps({"data": [{"id": UUID}]}).encode())
        if "resourceVersion" in params:
            attrs = revision_attrs or dict(NODE["attributes"])
            return FakeResponse(content=json.dumps(
                {"data": {**NODE, "attributes": attrs}}).encode())
        return FakeResponse(content=json.dumps({"data": NODE}).encode())

    return responder


@pytest.mark.asyncio
async def test_revision_get_reads_via_resource_version(monkeypatch):
    """JSON:API reads a specific revision with ?resourceVersion=id:<vid>."""
    fns = _register()
    requests = _capture(monkeypatch, _node_responder())

    result = await fns["revision_get"]("node/article", "1", "3")

    assert "error" not in result
    assert requests[-1]["url"] == f"https://example.test/jsonapi/node/article/{UUID}"
    assert requests[-1]["params"]["resourceVersion"] == "id:3"


@pytest.mark.asyncio
async def test_revision_get_no_longer_builds_a_revisions_path(monkeypatch):
    fns = _register()
    requests = _capture(monkeypatch, _node_responder())

    await fns["revision_get"]("node", "1", "3")

    assert not any("/revisions" in r["url"] for r in requests)
    assert not any("--" in r["url"] for r in requests)


@pytest.mark.asyncio
async def test_revision_list_reports_the_jsonapi_limitation(monkeypatch):
    fns = _register()
    _capture(monkeypatch, _node_responder())

    result = await fns["revision_list"]("node", "1")

    assert result["current"]["revision_id"] == 7
    assert result["revisions"] == []
    assert "405" in result["limitation"]


@pytest.mark.asyncio
async def test_revision_delete_does_not_issue_a_request(monkeypatch):
    """It used to DELETE /jsonapi/article/article/1/2, which cannot exist."""
    fns = _register()
    requests = _capture(monkeypatch)

    result = await fns["revision_delete"]("node", "1", "2")

    assert requests == []
    assert "405" in result["error"]


@pytest.mark.asyncio
async def test_revision_diff_compares_attribute_sets(monkeypatch):
    fns = _register()

    def responder(entry):
        params = entry["params"] or {}
        if any(k.startswith("filter[") for k in params):
            return FakeResponse(content=json.dumps({"data": [{"id": UUID}]}).encode())
        vid = 1 if params.get("resourceVersion") == "id:1" else 2
        return FakeResponse(content=json.dumps({
            "data": {"type": "node--article", "id": UUID,
                     "attributes": {"title": "Old" if vid == 1 else "New",
                                    "drupal_internal__vid": vid}}
        }).encode())

    _capture(monkeypatch, responder)

    result = await fns["revision_diff"]("node", "1", "1", "2")

    assert result["has_changes"] is True
    assert {"field": "title", "from": "Old", "to": "New"} in result["differences"]


@pytest.mark.asyncio
async def test_revision_revert_only_sends_changed_writable_fields(monkeypatch):
    """Structural fields must never be written back, or Drupal returns 400."""
    fns = _register()

    current_attrs = {
        "title": "New", "body": "new body", "drupal_internal__vid": 9,
        "drupal_internal__nid": 1, "uuid": UUID,
    }
    old_attrs = {
        "title": "Old", "body": "old body", "drupal_internal__vid": 7,
        "drupal_internal__nid": 1, "uuid": UUID,
    }
    requests = _capture(
        monkeypatch, _combined_responder(current_attrs, old_attrs)
    )

    result = await fns["revision_revert"]("node", "1", "7")

    assert result["reverted"] is True
    assert sorted(result["fields_changed"]) == ["body", "title"]

    patch = next(r for r in requests if r["method"] == "PATCH")
    sent = patch["json"]["data"]["attributes"]
    assert sent == {"title": "Old", "body": "old body"}
    assert "drupal_internal__vid" not in sent
    assert "drupal_internal__nid" not in sent
    assert "uuid" not in sent


def _combined_responder(current_attrs: dict, revision_attrs: dict):
    def responder(entry):
        params = entry["params"] or {}
        if any(k.startswith("filter[") for k in params):
            return FakeResponse(content=json.dumps({"data": [{"id": UUID}]}).encode())
        if "resourceVersion" in params:
            return FakeResponse(content=json.dumps(
                {"data": {**NODE, "attributes": revision_attrs}}).encode())
        return FakeResponse(content=json.dumps(
            {"data": {**NODE, "attributes": current_attrs}}).encode())
    return responder


@pytest.mark.asyncio
async def test_revision_revert_makes_no_request_when_already_current(monkeypatch):
    fns = _register()
    attrs = {"title": "Same", "drupal_internal__vid": 7, "uuid": UUID}
    requests = _capture(monkeypatch, _combined_responder(attrs, attrs))

    result = await fns["revision_revert"]("node", "1", "7")

    assert result["reverted"] is True
    assert result["fields_changed"] == []
    assert not any(r["method"] == "PATCH" for r in requests)


def test_entity_type_forms_are_normalised():
    assert revisions._type("node/article") == "node--article"
    assert revisions._type("node") == "node"
    assert revisions._type("/node/article/") == "node--article"


def test_all_five_revision_tools_are_registered():
    class FakeMCP:
        def __init__(self):
            self.names: list[str] = []

        def tool(self, *args, **kwargs):
            def decorate(fn):
                self.names.append(fn.__name__)
                return fn
            return decorate

    mcp = FakeMCP()
    revisions.register_tools(mcp, jsonapi_client=None)

    assert sorted(mcp.names) == sorted([
        "revision_list", "revision_get", "revision_revert",
        "revision_delete", "revision_diff",
    ])
