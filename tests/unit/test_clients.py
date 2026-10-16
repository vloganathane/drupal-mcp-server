"""Unit tests for Drupal clients."""

import asyncio
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
    DRUPAL_VERIFY_SSL = True


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        content: bytes = b'{"data": []}',
    ):
        self.status_code = status_code
        self.content = content

    @property
    def text(self) -> str:
        return self.content.decode() if self.content else ""

    def json(self) -> Any:
        return json.loads(self.content or b"{}")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code} error",
                request=httpx.Request("GET", "https://example.test/x"),
                response=self,  # type: ignore[arg-type]
            )


def _capture(
    monkeypatch: pytest.MonkeyPatch,
    responder: Any = None,
    default: FakeResponse | None = None,
) -> dict[str, Any]:
    """Patch httpx at the transport boundary so real client code runs end to end.

    ``AsyncClient.request`` is the single funnel every verb goes through, so
    patching it exercises the client's real URL building, header and payload
    logic rather than a mock's permissive signature.
    """
    seen: dict[str, Any] = {"requests": []}

    async def fake_request(self: Any, method: str, url: str, **kwargs: Any) -> FakeResponse:
        entry = {
            "method": method,
            "url": url,
            "params": kwargs.get("params"),
            "headers": kwargs.get("headers"),
            "json": kwargs.get("json"),
        }
        seen["requests"].append(entry)
        # Back-compat aliases pointing at the most recent request.
        for key, value in entry.items():
            seen[key] = value
        if responder is not None:
            return responder(entry)
        return default or FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request, raising=True)
    return seen


def test_jsonapi_client_exists():
    from drupal_mcp_server.clients import JSONAPIClient

    assert JSONAPIClient is not None


@pytest.mark.asyncio
async def test_get_by_id_accepts_params(monkeypatch: pytest.MonkeyPatch):
    """get_by_id must accept params, or every *_get tool raises TypeError."""
    client = JSONAPIClient(FakeSettings())
    seen = _capture(monkeypatch, default=FakeResponse())
    uuid = "4d9ecad4-49d5-481d-bf4e-8cfe9fde5471"

    await client.get_by_id("node--article", uuid, params={"include": "uid"})

    assert seen["url"] == f"https://example.test/jsonapi/node/article/{uuid}"
    assert seen["params"] == {"include": "uid"}


@pytest.mark.asyncio
async def test_get_by_id_without_params(monkeypatch: pytest.MonkeyPatch):
    client = JSONAPIClient(FakeSettings())
    uuid = "4d9ecad4-49d5-481d-bf4e-8cfe9fde5471"
    seen = _capture(monkeypatch, default=FakeResponse())

    await client.get_by_id("node--article", uuid)

    assert seen["params"] is None


@pytest.mark.asyncio
async def test_delete_tolerates_204_no_content(monkeypatch: pytest.MonkeyPatch):
    """Drupal DELETE returns 204 with an empty body; parsing it as JSON must not raise."""
    client = JSONAPIClient(FakeSettings())
    _capture(monkeypatch, default=FakeResponse(status_code=204, content=b""))
    uuid = "4d9ecad4-49d5-481d-bf4e-8cfe9fde5471"

    result = await client.delete_resource("node--article", uuid)

    assert result["deleted"] is True


@pytest.mark.asyncio
async def test_headers_include_auth(monkeypatch: pytest.MonkeyPatch):
    """AuthManager.get_headers is sync; awaiting it would drop all credentials."""

    class SyncAuth:
        def get_headers(self) -> dict[str, str]:
            return {"Authorization": "Basic abc"}

    client = JSONAPIClient(FakeSettings(), SyncAuth())
    seen = _capture(monkeypatch, default=FakeResponse())

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


# --- Regression tests: bugs found against a real Drupal (DDEV) site ----------


@pytest.mark.asyncio
async def test_bundle_resource_type_uses_slash_path(monkeypatch: pytest.MonkeyPatch):
    """``node--article`` is a *type*, not a path. Drupal serves ``/jsonapi/node/article``.

    Building the ``--`` form 404s on every collection call.
    """
    client = JSONAPIClient(FakeSettings())
    seen = _capture(monkeypatch, default=FakeResponse())

    await client.get_resource("node--article")

    assert seen["url"] == "https://example.test/jsonapi/node/article"
    assert "--" not in seen["url"]


@pytest.mark.asyncio
async def test_bare_entity_type_expands_via_index(monkeypatch: pytest.MonkeyPatch):
    """``node`` alone has no path; the JSON:API index supplies the bundles."""
    index = {
        "links": {
            "self": {"href": "https://example.test/jsonapi"},
            "node--article": {"href": "https://example.test/jsonapi/node/article"},
            "node--page": {"href": "https://example.test/jsonapi/node/page"},
        }
    }

    def responder(entry: dict[str, Any]) -> FakeResponse:
        if entry["url"].rstrip("/").endswith("/jsonapi"):
            return FakeResponse(content=json.dumps(index).encode())
        # One row per bundle so the merge is observable.
        bundle = entry["url"].rsplit("/", 1)[-1]
        return FakeResponse(
            content=json.dumps({"data": [{"id": f"uuid-{bundle}", "type": "node--x"}]}).encode()
        )

    client = JSONAPIClient(FakeSettings())
    _capture(monkeypatch, responder=responder)

    result = await client.get_resource("node")

    assert len(result["data"]) == 2  # both bundles merged
    assert {row["id"] for row in result["data"]} == {"uuid-article", "uuid-page"}


@pytest.mark.asyncio
async def test_internal_id_resolves_to_uuid(monkeypatch: pytest.MonkeyPatch):
    """Drupal addresses single resources by UUID; nid/uid/tid need a filter lookup."""
    uuid = "4d9ecad4-49d5-481d-bf4e-8cfe9fde5471"

    def responder(entry: dict[str, Any]) -> FakeResponse:
        params = entry["params"] or {}
        if any("drupal_internal__nid" in key for key in params):
            return FakeResponse(content=json.dumps({"data": [{"id": uuid}]}).encode())
        return FakeResponse()

    client = JSONAPIClient(FakeSettings())
    seen = _capture(monkeypatch, responder=responder)

    await client.get_by_id("node--article", "10")

    # The final request must be the UUID path, not /node/article/10.
    assert seen["requests"][-1]["url"] == f"https://example.test/jsonapi/node/article/{uuid}"


@pytest.mark.asyncio
async def test_write_payload_is_wrapped_in_data(monkeypatch: pytest.MonkeyPatch):
    """Flat tool payloads are rejected with 400 'must include a type'."""
    client = JSONAPIClient(FakeSettings())
    seen = _capture(monkeypatch, default=FakeResponse())

    await client.create_resource("node--article", {"title": "Hi", "type": "node--article"})

    assert seen["json"] == {
        "data": {"type": "node--article", "attributes": {"title": "Hi"}}
    }


@pytest.mark.asyncio
async def test_already_wrapped_payload_is_untouched(monkeypatch: pytest.MonkeyPatch):
    client = JSONAPIClient(FakeSettings())
    seen = _capture(monkeypatch, default=FakeResponse())
    doc = {"data": {"type": "node--article", "attributes": {"title": "Hi"}}}

    await client.create_resource("node--article", doc)

    assert seen["json"] == doc


@pytest.mark.asyncio
async def test_jsonapi_media_type_is_vnd_api_json(monkeypatch: pytest.MonkeyPatch):
    """``application/json`` gets 415 Unsupported Media Type from Drupal."""
    client = JSONAPIClient(FakeSettings())
    seen = _capture(monkeypatch, default=FakeResponse())

    await client.create_resource("node--article", {"title": "Hi", "type": "node--article"})

    assert seen["headers"]["Content-Type"] == "application/vnd.api+json"
    assert seen["headers"]["Accept"] == "application/vnd.api+json"


@pytest.mark.asyncio
async def test_update_payload_uses_resolved_uuid(monkeypatch: pytest.MonkeyPatch):
    """The body must carry the UUID even when the caller passed an nid."""
    uuid = "4d9ecad4-49d5-481d-bf4e-8cfe9fde5471"

    def responder(entry: dict[str, Any]) -> FakeResponse:
        params = entry["params"] or {}
        if any("drupal_internal__nid" in key for key in params):
            return FakeResponse(content=json.dumps({"data": [{"id": uuid}]}).encode())
        return FakeResponse()

    client = JSONAPIClient(FakeSettings())
    seen = _capture(monkeypatch, responder=responder)

    await client.update_resource("node--article", "10", {"title": "Renamed"})

    assert seen["json"]["data"]["id"] == uuid


@pytest.mark.asyncio
async def test_http_errors_include_drupal_detail(monkeypatch: pytest.MonkeyPatch):
    """Discarding the body turns 'must include a type' into a bare '400 Bad Request'."""
    body = json.dumps(
        {"errors": [{"title": "Bad Request", "detail": "Resource object must include a type."}]}
    ).encode()
    client = JSONAPIClient(FakeSettings())
    _capture(monkeypatch, default=FakeResponse(status_code=400, content=body))

    with pytest.raises(httpx.HTTPStatusError, match="must include a type"):
        await client.create_resource("node--article", {"title": "Hi"})


def test_verify_ssl_false_reaches_httpx(monkeypatch: pytest.MonkeyPatch):
    """Self-signed dev certs (DDEV/Lando) otherwise fail with no override."""
    captured: dict[str, Any] = {}
    original = httpx.AsyncClient.__init__

    def spy(self: Any, *args: Any, **kwargs: Any) -> None:
        captured.update(kwargs)
        original(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", spy)

    class InsecureSettings(FakeSettings):
        DRUPAL_VERIFY_SSL = False

    client = JSONAPIClient(InsecureSettings())
    assert client._verify_ssl is False

    # And it must be passed to httpx, not merely stored on the client.
    client._cookies = lambda: {}  # type: ignore[method-assign]
    client._client()
    assert captured["verify"] is False


# --- GraphQL schema ----------------------------------------------------------


@pytest.mark.asyncio
async def test_graphql_get_schema_uses_introspection(monkeypatch: pytest.MonkeyPatch):
    """graphql_schema_get called get_schema(), which did not exist."""
    from drupal_mcp_server.clients.graphql import GraphQLClient

    client = GraphQLClient(FakeSettings())
    seen = _capture(monkeypatch, default=FakeResponse())

    await client.get_schema()

    assert "__schema" in seen["json"]["query"]


@pytest.mark.asyncio
async def test_graphql_schema_sdl_renders(monkeypatch: pytest.MonkeyPatch):
    from drupal_mcp_server.clients.graphql import GraphQLClient

    schema = {
        "data": {
            "__schema": {
                "queryType": {"name": "QueryRoot"},
                "types": [
                    {"kind": "OBJECT", "name": "QueryRoot", "interfaces": [],
                     "fields": [{"name": "node", "args": [],
                                 "type": {"kind": "OBJECT", "name": "Node", "ofType": None}}]},
                    {"kind": "SCALAR", "name": "DateTime"},
                    {"kind": "ENUM", "name": "Status", "enumValues": [{"name": "ACTIVE"}]},
                    {"kind": "OBJECT", "name": "__Schema", "fields": []},
                ],
            }
        }
    }
    client = GraphQLClient(FakeSettings())
    _capture(
        monkeypatch,
        default=FakeResponse(content=json.dumps(schema).encode()),
    )

    sdl = await client.get_schema_sdl()

    assert "type QueryRoot" in sdl
    assert "node: Node" in sdl
    assert "scalar DateTime" in sdl
    assert "enum Status" in sdl
    assert "__Schema" not in sdl  # introspection types are not part of the API


@pytest.mark.asyncio
async def test_graphql_schema_sdl_reports_missing_introspection(monkeypatch: pytest.MonkeyPatch):
    from drupal_mcp_server.clients.graphql import GraphQLClient

    client = GraphQLClient(FakeSettings())
    _capture(monkeypatch, default=FakeResponse(content=b'{"data": {}}'))

    with pytest.raises(ValueError, match="GraphQL module"):
        await client.get_schema_sdl()


# --- Structural guard for the whole DEAD-tool bug class ----------------------


def test_no_tool_calls_a_missing_client_method():
    """Every ``jsonapi.foo()`` / ``graphql.foo()`` in a tool must exist.

    graphql_schema_get called get_schema() and get_schema_sdl(), neither of
    which existed, so the tool was dead on every call. This scans the tool
    modules so the same mistake cannot land again.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "src" / "drupal_mcp_server"
    clients = {
        "jsonapi": ("clients/jsonapi.py", "JSONAPIClient"),
        "graphql": ("clients/graphql.py", "GraphQLClient"),
        "drush": ("clients/drush.py", "DrushClient"),
        "ai": ("services/ai_service.py", "AIService"),
        "site_manager": ("services/site_manager.py", "SiteManager"),
    }

    def members(rel: str, cls: str) -> set[str]:
        tree = ast.parse((root / rel).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == cls:
                return {
                    s.name
                    for s in node.body
                    if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
        raise AssertionError(f"class {cls} not found in {rel}")

    available = {name: members(rel, cls) for name, (rel, cls) in clients.items()}

    missing: dict[str, list[str]] = {}
    for path in sorted((root / "tools").rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            base = node.func.value
            if isinstance(base, ast.Name) and base.id in available:
                if node.func.attr not in available[base.id]:
                    missing.setdefault(f"{base.id}.{node.func.attr}", []).append(
                        f"{path.name}:{node.lineno}"
                    )

    assert not missing, f"tools call methods that do not exist: {missing}"


# --- Drush -------------------------------------------------------------------


class _FakeProc:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", rc: int = 0):
        self._stdout, self._stderr, self.returncode = stdout, stderr, rc

    async def communicate(self):
        return self._stdout, self._stderr


def _fake_drush(monkeypatch, script, mod):
    """Patch subprocess creation; ``script`` maps argv -> _FakeProc."""
    calls: list[list[str]] = []

    async def fake_exec(*argv, **kwargs):
        calls.append(list(argv))
        return script(list(argv))

    mod._calls = calls
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    return calls


def _settings(**over):
    class S:
        DRUSH_PATH = "drush"
        DRUSH_ALIAS = "@self"
    for k, v in over.items():
        setattr(S, k, v)
    return S()


@pytest.mark.asyncio
async def test_drush_path_may_contain_arguments(monkeypatch: pytest.MonkeyPatch):
    """'ddev drush' must work for container-based local setups."""
    import drupal_mcp_server.clients.drush as mod
    from drupal_mcp_server.clients.drush import DrushClient

    calls = _fake_drush(monkeypatch, lambda argv: _FakeProc(b'{"ok":1}'), mod)

    await DrushClient(_settings(DRUSH_PATH="ddev drush")).run("status")

    assert calls[0][:2] == ["ddev", "drush"]


@pytest.mark.asyncio
async def test_drush_does_not_duplicate_format_flag(monkeypatch: pytest.MonkeyPatch):
    """Most tools already pass --format=json; appending it again is redundant."""
    import drupal_mcp_server.clients.drush as mod
    from drupal_mcp_server.clients.drush import DrushClient

    calls = _fake_drush(monkeypatch, lambda argv: _FakeProc(b"{}"), mod)

    await DrushClient(_settings()).run("status", ["--format=json"])

    assert calls[0].count("--format=json") == 1


@pytest.mark.asyncio
async def test_drush_retries_without_format_when_unsupported(monkeypatch: pytest.MonkeyPatch):
    """`drush cron` rejects --format entirely; the command should still run."""
    import drupal_mcp_server.clients.drush as mod
    from drupal_mcp_server.clients.drush import DrushClient

    def script(argv):
        if "--format=json" in argv:
            return _FakeProc(rc=1, stderr=b'The "--format" option does not exist.')
        return _FakeProc(b'{"ran": true}')

    calls = _fake_drush(monkeypatch, script, mod)

    result = await DrushClient(_settings()).run("cron")

    assert result["returncode"] == 0
    assert result["data"] == {"ran": True}
    assert "--format=json" not in calls[1]


@pytest.mark.asyncio
async def test_drush_never_offers_format_to_sql_query(monkeypatch: pytest.MonkeyPatch):
    """`sql:query` has no --format option on Drush 13, so the flag cost a
    full failed bootstrap before the retry on every database query."""
    import drupal_mcp_server.clients.drush as mod
    from drupal_mcp_server.clients.drush import DrushClient

    calls = _fake_drush(monkeypatch, lambda argv: _FakeProc(b"1\t2\n"), mod)

    await DrushClient(_settings()).run("sql:query", ["SELECT 1, 2"])

    assert len(calls) == 1
    assert "--format=json" not in calls[0]
    assert calls[0][2:4] == ["sql:query", "SELECT 1, 2"]


@pytest.mark.asyncio
async def test_drush_missing_binary_returns_actionable_error(monkeypatch: pytest.MonkeyPatch):
    """A bare FileNotFoundError makes every drush tool look broken."""
    from drupal_mcp_server.clients.drush import DrushClient

    async def raise_not_found(*argv, **kwargs):
        raise FileNotFoundError("drush")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", raise_not_found)

    result = await DrushClient(_settings()).run("status")

    assert result["returncode"] == 127
    assert "DRUSH_PATH" in result["stderr"]


@pytest.mark.asyncio
async def test_watchdog_tool_does_not_repeat_the_command(monkeypatch: pytest.MonkeyPatch):
    """It built 'watchdog:show --format=json watchdog:show --count=5 ...'."""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "src" / "drupal_mcp_server" / "tools"
    offenders = []
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr != "run" or len(node.args) < 2:
                continue
            first, second = node.args[0], node.args[1]
            if isinstance(first, ast.Constant) and isinstance(second, (ast.List, ast.Tuple)):
                if second.elts and isinstance(second.elts[0], ast.Constant) and second.elts[0].value == first.value:
                    offenders.append(f"{path.name}:{node.lineno}")

    assert not offenders, f"drush.run() called with the command repeated: {offenders}"


@pytest.mark.asyncio
async def test_payload_keeps_an_already_structured_resource_object(monkeypatch: pytest.MonkeyPatch):
    """Otherwise a document with attributes becomes attributes.attributes."""
    client = JSONAPIClient(FakeSettings())
    seen = _capture(monkeypatch, default=FakeResponse())
    uuid = "4d9ecad4-49d5-481d-bf4e-8cfe9fde5471"
    doc = {"id": uuid, "type": "node--article", "attributes": {"title": "Hi"}}

    await client.update_resource("node--article", uuid, doc)

    assert seen["json"] == {
        "data": {"id": uuid, "type": "node--article", "attributes": {"title": "Hi"}}
    }


def _capture_drush(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Record the argv DrushClient builds, without running anything."""
    from drupal_mcp_server.clients.drush import DrushClient

    seen: list[list[str]] = []

    async def fake_exec(self, cmd, cwd):
        seen.append(cmd)
        return {"returncode": 0, "data": {}, "stderr": "", "command": " ".join(cmd)}

    monkeypatch.setattr(DrushClient, "_exec", fake_exec, raising=True)
    return seen


@pytest.mark.asyncio
async def test_drush_accepts_a_splatted_command_line(monkeypatch: pytest.MonkeyPatch):
    """10 tools passed 4-8 positional tokens and crashed with a TypeError."""
    from drupal_mcp_server.clients.drush import DrushClient

    seen = _capture_drush(monkeypatch)
    cmd = ("feeds:import", "--feed-id", "1", "news", "--format=json")

    await DrushClient(_settings()).run(*cmd)

    assert seen[0] == ["drush", "@self", "feeds:import", "--feed-id", "1", "news", "--format=json"]


@pytest.mark.asyncio
async def test_drush_splits_a_quoted_argument_string(monkeypatch: pytest.MonkeyPatch):
    """`run("config:set", "a b c")` used to become one argument per character."""
    from drupal_mcp_server.clients.drush import DrushClient

    seen = _capture_drush(monkeypatch)

    await DrushClient(_settings()).run("config:set", "twig.config debug true")

    assert seen[0] == ["drush", "@self", "config:set", "--format=json", "twig.config", "debug", "true"]


@pytest.mark.asyncio
async def test_drush_mixed_string_and_list_arguments(monkeypatch: pytest.MonkeyPatch):
    from drupal_mcp_server.clients.drush import DrushClient

    seen = _capture_drush(monkeypatch)

    await DrushClient(_settings()).run("user:role:add", ["authenticated", "2"])
    await DrushClient(_settings()).run("pm:list", "--status=enabled", ["--format=json"])

    assert seen[0] == ["drush", "@self", "user:role:add", "--format=json", "authenticated", "2"]
    assert seen[1] == ["drush", "@self", "pm:list", "--status=enabled", "--format=json"]


@pytest.mark.asyncio
async def test_drush_with_no_command_reports_it_instead_of_raising(monkeypatch: pytest.MonkeyPatch):
    from drupal_mcp_server.clients.drush import DrushClient

    result = await DrushClient(_settings()).run()

    assert result["returncode"] == 1
    assert "No drush command" in result["stderr"]


@pytest.mark.asyncio
async def test_drush_reports_the_retry_not_the_rejected_command(monkeypatch: pytest.MonkeyPatch):
    """Returning the original made every failure read as a --format complaint,
    burying the real reason the command failed."""
    from drupal_mcp_server.clients.drush import DrushClient

    seen: list[list[str]] = []

    async def fake_exec(self, cmd, cwd):
        seen.append(cmd)
        if any(a.startswith("--format") for a in cmd):
            return {"returncode": 1, "data": {},
                    "stderr": 'The "--format" option does not exist.',
                    "command": " ".join(cmd)}
        return {"returncode": 1, "data": {},
                "stderr": "The following modules are required: migrate",
                "command": " ".join(cmd)}

    monkeypatch.setattr(DrushClient, "_exec", fake_exec, raising=True)

    result = await DrushClient(_settings()).run("migrate-status", ["d7_node_article"])

    assert len(seen) == 2
    assert result["returncode"] == 1
    assert "required: migrate" in result["stderr"]
    assert "--format" not in result["stderr"]
    assert result["format_flag_dropped"] is True
    assert "--format" not in result["command"]


class _FakeResponse:
    def __init__(self, status_code: int, body: bytes, url: str = "https://x/jsonapi"):
        self.status_code = status_code
        self.content = body
        self.text = body.decode(errors="replace")
        self.request = type("R", (), {"url": url})()

    def json(self):
        import json as _json

        return _json.loads(self.content)


def test_empty_body_names_the_url_and_the_usual_cause():
    """An empty response used to surface as `Expecting value: line 1 column 1
    (char 0)`, which reads like a client bug rather than a dying site."""
    from drupal_mcp_server.clients.base import DrupalBaseClient

    with pytest.raises(RuntimeError) as excinfo:
        DrupalBaseClient._decode(_FakeResponse(200, b""), "GET")

    message = str(excinfo.value)
    assert "https://x/jsonapi" in message
    assert "empty body" in message
    assert "composer install" in message


def test_non_json_body_is_reported_with_what_arrived():
    from drupal_mcp_server.clients.base import DrupalBaseClient

    with pytest.raises(RuntimeError, match="not JSON"):
        DrupalBaseClient._decode(_FakeResponse(500, b"<html>fatal error</html>"), "GET")


def test_delete_and_204_are_allowed_to_be_empty():
    from drupal_mcp_server.clients.base import DrupalBaseClient

    assert DrupalBaseClient._decode(_FakeResponse(204, b""), "GET") == {}
    assert DrupalBaseClient._decode(_FakeResponse(200, b""), "DELETE") == {}


# --- Argument construction -------------------------------------------------


def test_list_arguments_are_passed_through_as_single_tokens():
    """Anything holding a space was shlex-split into separate argv entries.

    Against a live site `sql:query ["SHOW TABLES"]` reached drush as two
    arguments and answered "Too many arguments", so db_tables, db_query,
    db_count and drush_php_eval all failed, as did every tool running `ev`.
    """
    from drupal_mcp_server.clients.drush import DrushClient

    flatten = DrushClient._flatten

    assert flatten([["SHOW TABLES"]]) == ["SHOW TABLES"]
    assert flatten([["SELECT COUNT(*) as c FROM node"]]) == ["SELECT COUNT(*) as c FROM node"]
    assert flatten([["user:role:add", "administrator", "admin", "--yes"]]) == [
        "user:role:add", "administrator", "admin", "--yes",
    ]
    # Quotes must survive so PHP and SQL keep their string boundaries.
    assert flatten(['print json_encode(["a" => 1]);']) == [
        "print", "json_encode([a", "=>", "1]);",
    ]
    assert flatten([['print json_encode(["a" => 1]);']]) == ['print json_encode(["a" => 1]);']


def test_list_arguments_keep_empty_and_drop_none():
    from drupal_mcp_server.clients.drush import DrushClient

    flatten = DrushClient._flatten

    # Inside a list an empty string is a real, if odd, argv token.
    assert flatten([["", "a"]]) == ["", "a"]
    assert flatten([[None, "a", None]]) == ["a"]
    # A bare empty string part is dropped, as it always was.
    assert flatten([None, "", "x"]) == ["x"]


def test_list_arguments_are_not_character_split():
    """A string used to be treated as a sequence of characters."""
    from drupal_mcp_server.clients.drush import DrushClient

    assert DrushClient._flatten(["cron"]) == ["cron"]
