"""The sweep is the only thing that ever sees all 366 tools.

A bug in how it chooses arguments, or in how it reads an answer back, does not
fail anything -- it quietly mislabels the whole report, and the report is the
deliverable. Two such bugs are pinned here: a `langcode` filled with junk made
create_term answer 403 about a field permission instead of running, and
`ddev_exec` was handed `status`, which is a drush command and not a shell one.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

_LIVE = Path(__file__).resolve().parents[1] / "live" / "sweep.py"


@pytest.fixture(scope="module")
def sweep() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sweep_live", _LIVE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_optional_langcode_is_omitted(sweep: ModuleType) -> None:
    """JSON:API write-protects `langcode` on a multilingual site whatever the
    value, so sending one costs the tool a 403 it did not cause."""
    schema = {
        "properties": {
            "vid": {"type": "string"},
            "name": {"type": "string"},
            "langcode": {"type": "string", "default": None},
        },
        "required": ["vid", "name"],
    }

    assert sweep.synthesize(schema) == {"vid": "tags", "name": "sweep_name"}


def test_required_langcode_still_gets_a_value(sweep: ModuleType) -> None:
    """A caller who named the argument cannot have it dropped -- that is a
    missing_argument, which the server refuses and the sweep used to count
    as a pass."""
    schema = {
        "properties": {
            "langcode": {"type": "string"},
            "translation": {"type": "object"},
        },
        "required": ["langcode", "translation"],
    }

    assert sweep.synthesize(schema)["langcode"] == "en"


def test_container_tools_get_a_command_the_container_has(sweep: ModuleType) -> None:
    """`ddev_exec` runs its argument inside the container, where `status` --
    the right answer for drush_command -- is not a command at all."""
    schema = {"properties": {"command": {"type": "string"}}}

    assert sweep.synthesize(schema, "ddev_exec")["command"] == "php -v"
    assert sweep.synthesize(schema, "lando_exec")["command"] == "php -v"
    assert sweep.synthesize(schema, "drush_command")["command"] == "status"


def test_queue_run_uses_a_queue_that_exists(sweep: ModuleType) -> None:
    schema = {"properties": {"queue_name": {"type": "string"}}}
    sweep.EXISTING_QUEUE = "real_queue"
    try:
        assert sweep.synthesize(schema, "queue_run")["queue_name"] == "real_queue"
    finally:
        sweep.EXISTING_QUEUE = ""

    # With nothing found, the name falls through rather than being blank: a
    # queue that is not there is an honest answer to report.
    schema_default = {"properties": {"queue_name": {"type": "string"}}}
    assert sweep.synthesize(schema_default, "queue_run")["queue_name"] == "sweep_name"


def test_a_failed_drush_run_is_not_counted_ok(sweep: ModuleType) -> None:
    """A Drush failure carries no `error` key, so the fall-through used to
    read `data: {}` as an empty success for db_query, db_tables and every
    `ev` tool."""
    verdict, detail = sweep.classify(
        {"returncode": 1, "stderr": "Could not connect to database"},
        "db_query",
        False,
    )

    assert verdict == "REJECTED"
    assert "Could not connect" in detail


def test_a_broken_tool_is_still_dead(sweep: ModuleType) -> None:
    """Reaching Drupal is what the change above protects; a tool that fails
    the same way on every call is still DEAD rather than merely rejected."""
    verdict, _ = sweep.classify(
        {"returncode": 1, "stderr": "Too many arguments"}, "db_tables", False
    )

    assert verdict == "DEAD"


def test_a_passing_run_stays_ok(sweep: ModuleType) -> None:
    assert sweep.classify({"data": {"rows": [1]}, "returncode": 0}, "db_query", False) == (
        "OK",
        "",
    )


# --- fixtures ------------------------------------------------------------
#
# Before these, every parameter ending in "id" was answered with the fixture
# node's id. `view_id`, `menu_id`, `webform_id` and eighty-odd others were all
# sent the same node number, so the tool answered a lookup miss and the sweep
# filed it as a refusal. That was 84 of 174 refusals in the run before the
# fixtures existed: not tools refusing, but the harness asking the wrong
# question. A miss says nothing about whether a tool works.


def test_a_read_only_tool_gets_a_real_id_for_its_resource(sweep: ModuleType) -> None:
    for tool, param, expected in [
        ("views_get", "view_id", "content"),
        ("menu_get", "menu_id", "main"),
        ("webform_get", "webform_id", "contact"),
        ("paragraphs_type_get", "type_id", "basic"),
        ("workflow_get", "workflow_id", "editorial"),
        ("media_type_get", "media_type_id", "image"),
    ]:
        schema = {"properties": {param: {"type": "string"}}}
        assert sweep.synthesize(schema, tool)[param] == expected, f"{tool}.{param}"


def test_config_id_means_what_the_tools_name_says_it_means(sweep: ModuleType) -> None:
    """One parameter name covers three different resources.

    `config_id` is a field config for field_config_*, a metatag config for
    metatag_config_*, and a search index for search_api_index_*. Handing all
    three the same value tests none of them.
    """
    schema = {"properties": {"config_id": {"type": "string"}}}
    assert (
        sweep.synthesize(schema, "field_config_get")["config_id"]
        == "media.image.field_media_image"
    )
    assert (
        sweep.synthesize(schema, "field_storage_get")["config_id"]
        == "media.field_media_image"
    )
    assert (
        sweep.synthesize(schema, "metatag_config_get")["config_id"] == "node.article"
    )


def test_a_mutating_tool_keeps_a_synthetic_id(sweep: ModuleType) -> None:
    """The sweep must not rewrite the site out from under itself.

    `views_update` with a real view id would save the view back with the
    arguments the harness synthesised, and every later `views_execute` would
    run against a view this run broke. Structural writes keep junk ids so
    they are refused rather than applied.
    """
    schema = {"properties": {"view_id": {"type": "string"}}}
    assert sweep.synthesize(schema, "views_update")["view_id"] == "sweep_value"
    assert sweep.synthesize(schema, "views_get")["view_id"] == "content"


def test_the_mutating_rule_catches_every_write_suffix(sweep: ModuleType) -> None:
    for tool in [
        "views_delete", "menu_link_delete", "field_config_update",
        "webform_delete", "node_delete", "moderation_state_delete",
        "user_block", "user_unblock", "comment_approve", "cache_clear",
        "config_import", "queue_purge",
    ]:
        assert sweep.MUTATING.search(tool), tool

    for tool in [
        "views_get", "views_list", "views_execute", "views_export",
        "webform_handler_list", "queue_list", "db_query", "search_index_get",
    ]:
        assert not sweep.MUTATING.search(tool), tool


def test_interface_translations_name_a_language_that_has_translations(
    sweep: ModuleType,
) -> None:
    """The interface translation tools operate on locale's target-language rows.

    This site's translations are French, so omitting the language lists
    nothing and writing one would create an English translation of English
    source text. JSON:API write-protection still applies everywhere else.
    """
    schema = {"properties": {"langcode": {"type": "string"}}}
    assert (
        sweep.synthesize(schema, "interface_translation_list")["langcode"] == "fr"
    )
    # A JSON:API write still omits it: sending one there is a 403 about a
    # field permission that says nothing about the tool.
    assert "langcode" not in sweep.synthesize(schema, "create_term")


def test_a_tool_that_names_a_node_id_is_the_one_that_triggers_a_recheck(
    sweep: ModuleType,
) -> None:
    """`delete_node` takes the fixture with it mid-sweep.

    revision_list, revision_get, revision_revert, revision_diff,
    translation_status, translation_add, moderation_transition_execute,
    layout_builder_override_remove and accessibility_aria_validate all 404'd
    for that reason alone. Only tools that actually declare a node id pay
    for the existence check.
    """
    assert sweep._takes_a_node_id({"properties": {"nid": {"type": "string"}}})
    assert sweep._takes_a_node_id({"properties": {"node_id": {"type": "string"}}})
    assert not sweep._takes_a_node_id({"properties": {"view_id": {"type": "string"}}})
    assert not sweep._takes_a_node_id({"properties": {}})


class _Response:
    """The one piece of urlopen's interface that json.load() actually uses."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self, *args) -> bytes:
        return self._body

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args) -> bool:
        return False


def _seed_bundles(sweep: ModuleType, monkeypatch) -> None:
    """Skip the index read so these tests only exercise the question asked."""
    monkeypatch.setattr(sweep, "_NODE_COLLECTIONS", ["https://example.test/jsonapi/node/article"])


def test_a_missing_node_is_reported_missing(sweep: ModuleType, monkeypatch) -> None:
    """Gone means "the filter matched nothing", not "the request 404'd".

    JSON:API addresses rows by uuid, so there is no direct URL for the node id
    the harness holds. The obvious `/jsonapi/node--article/7` builds the
    resource *name* into the path and 404s for every node -- including the
    ones that exist -- which made the fixture look permanently gone and
    re-provision itself on every check.

    A 5xx or a timeout is the server failing to answer rather than the node
    going away, and re-provisioning on one would churn the fixture for
    nothing. The same goes for an index that cannot be read at all.
    """
    import urllib.error

    _seed_bundles(sweep, monkeypatch)

    monkeypatch.setattr(
        sweep.urllib.request, "urlopen", lambda *a, **k: _Response(b'{"data": []}')
    )
    assert sweep.node_exists("7") is False

    monkeypatch.setattr(
        sweep.urllib.request, "urlopen", lambda *a, **k: _Response(b'{"data": [{"id": "u"}]}')
    )
    assert sweep.node_exists("7") is True

    def http_error(code: int) -> urllib.error.HTTPError:
        return urllib.error.HTTPError("u", code, "boom", {}, None)

    monkeypatch.setattr(
        sweep.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(http_error(500))
    )
    assert sweep.node_exists("7") is True

    def timeout(*a, **k):
        raise TimeoutError("slow")

    monkeypatch.setattr(sweep.urllib.request, "urlopen", timeout)
    assert sweep.node_exists("7") is True

    # No index, no answer -- and no fixture churn on a blip.
    monkeypatch.setattr(sweep, "_NODE_COLLECTIONS", None)
    assert sweep.node_exists("7") is True


def test_node_collections_uses_the_paths_the_index_advertises(
    sweep: ModuleType, monkeypatch
) -> None:
    """The resource name in the index is not its path.

    `node--article` is served at `/jsonapi/node/article`, so building the name
    into the URL -- as node_exists used to -- 404s for nodes that are there.
    """
    monkeypatch.setattr(sweep, "BASE", "https://127.0.0.1:64653")
    monkeypatch.setattr(sweep, "_NODE_COLLECTIONS", None)

    def fake_get(url: str, timeout: int = 30) -> dict:
        if url.endswith("/jsonapi"):
            return {
                "links": {
                    "node--article": {"href": "http://127.0.0.1:64653/jsonapi/node/article"},
                    "node--page": {"href": "http://127.0.0.1:64653/jsonapi/node/page"},
                    "taxonomy_term--tags": {"href": "http://example.test/jsonapi/tt/tags"},
                }
            }
        return {"data": [{"attributes": {"drupal_internal__nid": 12}}]}

    monkeypatch.setattr(sweep, "_get", fake_get)

    assert sweep.node_collections() == [
        "https://127.0.0.1:64653/jsonapi/node/article",
        "https://127.0.0.1:64653/jsonapi/node/page",
    ]
    # Read once: the bundles cannot change during a run, and asking again on
    # every existence check would double the request volume for nothing.
    assert sweep.node_collections() == sweep.node_collections()
    assert sweep.pick_live_nid() == "12"


def test_links_the_site_generates_are_followed_on_this_run_s_origin(
    sweep: ModuleType, monkeypatch
) -> None:
    """Drupal answers `http://` when it is reached through a port-mapped HTTPS
    endpoint. Following such a link sends plain HTTP to a TLS listener and
    nginx answers 400, which killed the sweep before it called a single tool.
    """
    monkeypatch.setattr(sweep, "BASE", "https://127.0.0.1:64653")

    assert sweep._origin() == "https://127.0.0.1:64653"
    assert (
        sweep._reanchor("http://127.0.0.1:64653/jsonapi/node/article")
        == "https://127.0.0.1:64653/jsonapi/node/article"
    )
    assert (
        sweep._reanchor("http://drupal-live.ddev.site/jsonapi/node/article?page=1")
        == "https://127.0.0.1:64653/jsonapi/node/article?page=1"
    )
    # A relative link already points at this run's origin.
    assert sweep._reanchor("/jsonapi/node/article") == "/jsonapi/node/article"


def test_fields_is_sent_as_a_payload_not_an_empty_object(sweep: ModuleType) -> None:
    """`create_node` answered "title is required", and updates were no-ops.

    Both came from one shadowing: `fields` on a content tool is a nested object,
    so `resolve_schema` reports its type as `object` and the `t == "object"`
    branch answered `{}` before the rule that knew what `fields` was for. An
    update that changes nothing still reports OK, so those tools kept their
    verdict while never actually being exercised -- which is why the symptom
    showed up on exactly one of the sixteen that declare the parameter.

    The payload is only for the object shape. `fields` is also the name of a
    plain list of field names on `query_nodes`, `jsonapi_sparse_fieldsets` and
    the views tools, and sending those a dict fails FastMCP's validation before
    the tool runs -- turning three passing tools into three refusals.
    """
    nested = {
        "properties": {
            "fields": {"type": "object", "properties": {"title": {"type": "string"}}}
        }
    }
    assert sweep.synthesize(nested, "create_node") == {"fields": {"title": "Sweep Title"}}
    assert sweep.synthesize(nested, "update_node") == {"fields": {"title": "Sweep Title"}}

    listed = {"properties": {"fields": {"type": "array", "items": {"type": "string"}}}}
    assert sweep.synthesize(listed, "query_nodes") == {"fields": []}

    # An object that is not `fields` is still sent empty rather than filled
    # with junk the tool would then have to reject.
    other = {"properties": {"options": {"type": "object"}}}
    assert sweep.synthesize(other, "some_tool") == {"options": {}}


def test_only_narrows_a_run_without_changing_the_rest(sweep: ModuleType) -> None:
    """A targeted re-run has to be able to name its tools.

    `only` was a single substring, so re-checking the tools whose verdicts one
    fix could have moved meant re-running all 367 -- against a host that may
    already be busy. A comma-separated list narrows it, and a run that is
    narrowed says so in its output file rather than overwriting the full
    sweep's results with the handful of tools it covered.
    """
    tools = [
        type("T", (), {"name": n})()
        for n in ("create_node", "update_node", "views_create", "queue_list")
    ]

    assert [t.name for t in sweep.select_tools(tools, None)] == [
        "create_node",
        "update_node",
        "views_create",
        "queue_list",
    ]
    assert [t.name for t in sweep.select_tools(tools, "create")] == [
        "create_node",
        "views_create",
    ]
    assert [t.name for t in sweep.select_tools(tools, "create_node, queue_list")] == [
        "create_node",
        "queue_list",
    ]
    # A pattern that matches nothing runs nothing, rather than everything.
    assert sweep.select_tools(tools, "nothing_matches_this") == []


def test_the_fixture_is_re_provisioned_when_a_tool_deletes_it(
    sweep: ModuleType, monkeypatch
) -> None:
    seen = {"checked": 0}

    def exists(nid: str) -> bool:
        seen["checked"] += 1
        return False

    monkeypatch.setattr(sweep, "node_exists", exists)
    monkeypatch.setattr(sweep, "pick_live_nid", lambda: "99")
    monkeypatch.setattr(sweep, "EXISTING_NID", "7")

    assert sweep.refresh_nid_if_gone() == "99"
    assert seen["checked"] == 1

    # Once re-provisioned it is not re-checked until it vanishes again.
    assert sweep.refresh_nid_if_gone() == "99"
    assert seen["checked"] == 2
