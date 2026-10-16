"""Unit tests for the site-insight tools added in Wave 2.

`find_entity_references` reads field configuration over JSON:API,
`search_entities` and `find_entity_by_path` run read-only SQL through
Drush, and `config_status` reads `drush config:status`. The SQL strings
are asserted here as well as the results: the search and alias queries
are built from caller input, so the escaping is part of the contract.
"""

from typing import Any

import drupal_mcp_server.tools.analysis as analysis
import drupal_mcp_server.tools.config as config_tools


def _tool_functions(module: Any, **deps: Any) -> dict[str, Any]:
    class FakeMCP:
        def __init__(self) -> None:
            self.fns: dict[str, Any] = {}

        def tool(self, *args: Any, **kwargs: Any):
            def decorate(fn):
                self.fns[fn.__name__] = fn
                return fn

            return decorate

    mcp = FakeMCP()
    module.register_tools(mcp, **deps)
    return mcp.fns


class _JSONAPI:
    """Canned JSON:API: resource lists, entities by id, an index."""

    def __init__(
        self,
        resources: dict[str, list[dict[str, Any]]] | None = None,
        entities: dict[tuple[str, str], dict[str, Any]] | None = None,
    ) -> None:
        self.resources = resources or {}
        self.entities = entities or {}
        self.resource_calls: list[tuple[str, dict[str, Any] | None]] = []
        self.by_id_calls: list[tuple[str, str]] = []

    async def get_resource(self, resource_type: str, params: dict[str, Any] | None = None):
        self.resource_calls.append((resource_type, params))
        return {"data": self.resources.get(resource_type, [])}

    async def get_by_id(self, resource_type: str, resource_id: str, params: Any = None):
        self.by_id_calls.append((resource_type, str(resource_id)))
        key = (resource_type, str(resource_id))
        if key not in self.entities:
            raise RuntimeError("404 Not Found")
        return self.entities[key]


class _Drush:
    """sql:query answered by a handler; a dict answers by command name."""

    def __init__(self, handler: Any) -> None:
        self.handler = handler
        self.calls: list[tuple[str, list[str]]] = []

    async def run(self, command: str, args: list[str] | None = None, **kwargs: Any):
        self.calls.append((command, list(args or [])))
        if callable(self.handler):
            return self.handler(list(args or []))
        return self.handler.get(command, {"returncode": 0, "data": {}})


def test_find_entity_references_lists_every_bundle_using_a_targeting_field():
    import asyncio

    jsonapi = _JSONAPI(
        resources={
            "field_storage_config--field_storage_config": [
                {
                    "drupal_internal__id": "node.field_tags",
                    "field_name": "field_tags",
                    "entity_type": "node",
                    "field_storage_config_type": "entity_reference",
                    "settings": {"target_type": "taxonomy_term"},
                },
                {
                    "drupal_internal__id": "node.field_hero",
                    "field_name": "field_hero",
                    "entity_type": "node",
                    "field_storage_config_type": "entity_reference",
                    "settings": {"target_type": "media"},
                },
                {
                    "drupal_internal__id": "node.field_weight",
                    "field_name": "field_weight",
                    "entity_type": "node",
                    "field_storage_config_type": "integer",
                    "settings": {},
                },
            ],
            "field_config--field_config": [
                {"entity_type": "node", "bundle": "article", "field_name": "field_tags", "drupal_internal__id": "node.article.field_tags"},
                {"entity_type": "node", "bundle": "page", "field_name": "field_tags", "drupal_internal__id": "node.page.field_tags"},
                {"entity_type": "node", "bundle": "article", "field_name": "field_hero", "drupal_internal__id": "node.article.field_hero"},
                {"entity_type": "node", "bundle": "article", "field_name": "field_weight", "drupal_internal__id": "node.article.field_weight"},
            ],
        }
    )
    fns = _tool_functions(analysis, jsonapi_client=jsonapi, drush_client=None)

    result = asyncio.run(fns["find_entity_references"]("taxonomy_term"))

    rows = result["reference_fields"]
    # Only storages whose settings target taxonomy_term count; the media
    # reference and the plain integer field are not references to it.
    assert [(r["bundle"], r["field_name"]) for r in rows] == [
        ("article", "field_tags"),
        ("page", "field_tags"),
    ]
    assert result["by_source_entity_type"] == {"node": 2}
    assert result["total"] == 2
    # The double path Drupal serves config entities at is asked for, and
    # the storage's field type rides along.
    assert rows[0]["field_type"] == "entity_reference"
    assert [c[0] for c in jsonapi.resource_calls[:2]] == [
        "field_storage_config--field_storage_config",
        "field_config--field_config",
    ]


def test_find_entity_references_filters_by_bundle_and_field_name():
    import asyncio

    jsonapi = _JSONAPI(
        resources={
            "field_storage_config--field_storage_config": [
                {
                    "drupal_internal__id": "node.field_tags",
                    "field_name": "field_tags",
                    "entity_type": "node",
                    "field_storage_config_type": "entity_reference",
                    "settings": {"target_type": "taxonomy_term"},
                }
            ],
            "field_config--field_config": [
                {"entity_type": "node", "bundle": "article", "field_name": "field_tags", "drupal_internal__id": "node.article.field_tags"},
                {"entity_type": "node", "bundle": "page", "field_name": "field_tags", "drupal_internal__id": "node.page.field_tags"},
            ],
        }
    )
    fns = _tool_functions(analysis, jsonapi_client=jsonapi, drush_client=None)

    by_bundle = asyncio.run(
        fns["find_entity_references"]("taxonomy_term", bundle="page")
    )
    by_field = asyncio.run(
        fns["find_entity_references"]("taxonomy_term", field_name="field_tags")
    )
    bad = asyncio.run(fns["find_entity_references"]("taxonomy term; DROP TABLE x"))
    bad_limit = asyncio.run(fns["find_entity_references"]("node", limit=0))

    assert [r["bundle"] for r in by_bundle["reference_fields"]] == ["page"]
    assert by_field["total"] == 2
    assert "Invalid entity_type" in bad["error"]
    assert "limit must be" in bad_limit["error"]


def test_search_entities_runs_one_union_query_and_escapes_the_term():
    """Six tables in one UNION: on a containerized site each drush call
    pays a full bootstrap, and the output is raw tab-separated text."""
    import asyncio

    seen_sql: list[str] = []

    def handler(args: list[str]) -> dict[str, Any]:
        seen_sql.append(args[0])
        return {
            "returncode": 0,
            "data": {
                "output": (
                    "node\t4\tO'Brien 100% notes\tarticle\n"
                    "node\t11\tO'Brien's other\tarticle\n"
                )
            },
        }

    drush = _Drush(handler)
    fns = _tool_functions(analysis, jsonapi_client=None, drush_client=drush)

    result = asyncio.run(fns["search_entities"]("O'Brien_100%"))

    assert result["total"] == 2
    assert result["results"]["node"][0] == {
        "id": "4",
        "label": "O'Brien 100% notes",
        "extra": "article",
    }
    assert result["matches"] == {"node": 2}
    assert "skipped" not in result
    # A single statement asked for all six tables...
    assert len(seen_sql) == 1
    assert "UNION ALL" in seen_sql[0]
    # ...with the wildcards and quotes escaped, once per table.
    assert seen_sql[0].count("LIKE '%O\\'Brien\\_100\\%%'") == 6
    assert seen_sql[0].count("UNION ALL") == 5


def test_search_entities_falls_back_per_table_when_a_table_is_missing():
    """One missing table (media off, minimal profile) takes the whole UNION
    down; the per-table retry skips only what is actually absent."""
    import asyncio

    seen_sql: list[str] = []

    def handler(args: list[str]) -> dict[str, Any]:
        sql = args[0]
        seen_sql.append(sql)
        if "UNION ALL" in sql:
            return {
                "returncode": 1,
                "data": {},
                "stderr": "SQLSTATE[42S02]: Table 'db.media_field_data' doesn't exist",
            }
        if "node_field_data" in sql:
            return {
                "returncode": 0,
                "data": {"output": "node\t4\tLegacy node\tarticle\n"},
            }
        if "media_field_data" in sql:
            return {
                "returncode": 1,
                "data": {},
                "stderr": "SQLSTATE[42S02]: Table 'db.media_field_data' doesn't exist",
            }
        return {"returncode": 0, "data": {"output": ""}}

    drush = _Drush(handler)
    fns = _tool_functions(analysis, jsonapi_client=None, drush_client=drush)

    result = asyncio.run(fns["search_entities"]("legacy", entity_types=["node", "media"]))

    assert result["results"]["node"] == [
        {"id": "4", "label": "Legacy node", "extra": "article"}
    ]
    assert "media_field_data" in result["skipped"]["media"]
    # The union attempt plus one retry per requested type.
    assert len(seen_sql) == 3


def test_search_entities_validates_input():
    import asyncio

    drush = _Drush(lambda args: {"returncode": 0, "data": []})
    fns = _tool_functions(analysis, jsonapi_client=None, drush_client=drush)

    empty = asyncio.run(fns["search_entities"]("   "))
    long = asyncio.run(fns["search_entities"]("x" * 65))
    unknown = asyncio.run(fns["search_entities"]("x", entity_types=["node", "wombat"]))
    limit = asyncio.run(fns["search_entities"]("x", limit=500))

    assert "1 to 64 characters" in empty["error"]
    assert "1 to 64 characters" in long["error"]
    assert "wombat" in unknown["error"]
    assert "limit must be" in limit["error"]
    # Nothing reached the database.
    assert drush.calls == []


def test_find_entity_by_path_reads_an_internal_route_directly():
    import asyncio

    jsonapi = _JSONAPI(
        entities={("node", "5"): {"id": "5", "type": "node", "title": "About"}}
    )
    drush = _Drush(lambda args: {"returncode": 0, "data": []})
    fns = _tool_functions(analysis, jsonapi_client=jsonapi, drush_client=drush)

    result = asyncio.run(fns["find_entity_by_path"]("/node/5"))

    assert result["found"] is True
    assert result["entity_type"] == "node"
    assert result["entity_id"] == "5"
    assert result["entity"]["title"] == "About"
    # A direct route needs no alias lookup.
    assert drush.calls == []


def test_find_entity_by_path_resolves_an_alias_before_the_route():
    import asyncio

    jsonapi = _JSONAPI(
        entities={("node", "7"): {"id": "7", "type": "node", "title": "Our story"}}
    )

    def handler(args: list[str]) -> dict[str, Any]:
        if "path_alias" in args[0]:
            return {
                "returncode": 0,
                "data": {"output": "1\t/our-story\t/node/7\ten\n"},
            }
        return {"returncode": 0, "data": {"output": ""}}

    drush = _Drush(handler)
    fns = _tool_functions(analysis, jsonapi_client=jsonapi, drush_client=drush)

    from_url = asyncio.run(fns["find_entity_by_path"]("https://example.test/our-story?page=2"))
    bare = asyncio.run(fns["find_entity_by_path"]("/our-story"))

    assert from_url["found"] is True
    assert from_url["internal_path"] == "/node/7"
    assert from_url["alias"]["path"] == "/node/7"
    assert bare["entity_id"] == "7"
    alias_sql = drush.calls[0][1][0]
    assert "WHERE alias = '/our-story'" in alias_sql


def test_find_entity_by_path_reports_a_miss_and_a_stale_alias():
    import asyncio

    jsonapi = _JSONAPI(entities={})

    def handler(args: list[str]) -> dict[str, Any]:
        # Answer only for the alias the query asks about: a fake that
        # returns a row for every lookup would make the miss case a hit.
        if "path_alias" in args[0] and "'/gone'" in args[0]:
            return {
                "returncode": 0,
                "data": {"output": "9\t/gone\t/node/99\ten\n"},
            }
        return {"returncode": 0, "data": {"output": ""}}

    fns = _tool_functions(analysis, jsonapi_client=jsonapi, drush_client=_Drush(handler))

    miss = asyncio.run(fns["find_entity_by_path"]("/nothing-like-this"))
    stale = asyncio.run(fns["find_entity_by_path"]("/gone"))

    assert miss["found"] is False
    assert "No route pattern or path alias" in miss["note"]
    # The alias resolved, but the node behind it is gone.
    assert stale["found"] is False
    assert "404" in stale["error"]


def test_config_status_counts_states_and_flags_an_empty_sync_directory():
    import asyncio

    drush = _Drush(
        {
            "config:status": {
                "returncode": 0,
                "data": {
                    "node.type.article": {"name": "node.type.article", "state": "Same"},
                    "block.block.foo": {"name": "block.block.foo", "state": "Only in DB"},
                    "field.storage.node.body": {
                        "name": "field.storage.node.body",
                        "state": "Different",
                    },
                },
            }
        }
    )
    fns = _tool_functions(config_tools, drush_client=drush)

    result = asyncio.run(fns["config_status"]())

    assert result["counts"] == {"Same": 1, "Only in DB": 1, "Different": 1}
    assert result["total"] == 3
    assert result["objects"]["Different"]["names"] == ["field.storage.node.body"]


def test_config_status_explains_an_empty_sync_directory():
    import asyncio

    names = {f"node.type.t{i}": {"state": "Only in DB"} for i in range(3)}
    drush = _Drush({"config:status": {"returncode": 0, "data": names}})
    fns = _tool_functions(config_tools, drush_client=drush)

    result = asyncio.run(fns["config_status"]())

    assert result["counts"] == {"Only in DB": 3}
    assert "sync directory is empty" in result["note"]


def test_config_status_surfaces_drush_failures():
    import asyncio

    drush = _Drush(
        {
            "config:status": {
                "returncode": 1,
                "data": {},
                "stderr": "no configuration management",
            }
        }
    )
    fns = _tool_functions(config_tools, drush_client=drush)

    result = asyncio.run(fns["config_status"]())

    assert "no configuration management" in result["error"]
