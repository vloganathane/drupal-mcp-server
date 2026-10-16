"""Tests for migration plan helpers and service."""

from unittest.mock import AsyncMock

import pytest

from drupal_mcp_server.services.migration_service import MigrationService
from drupal_mcp_server.tools.migration import register_tools


def _capture_tools(register_func, **deps):
    from unittest.mock import MagicMock

    mock_mcp = MagicMock()
    registered = []

    def decorator():
        def wrapper(f):
            registered.append(f)
            return f

        return wrapper

    mock_mcp.tool = MagicMock(side_effect=decorator)
    register_func(mock_mcp, **deps)
    return registered


def _find(tools, name):
    for tool in tools:
        if tool.__name__ == name:
            return tool
    raise ValueError(name)


@pytest.fixture
def tmp_service(tmp_path):
    return MigrationService(storage_dir=tmp_path)


class TestMigrationService:
    @pytest.mark.asyncio
    async def test_plan_lifecycle(self, tmp_service):
        plan = tmp_service.create_plan(
            "m1",
            source={"url": "https://old.example.com"},
            target={"url": "https://new.example.com"},
            entities=["user--user"],
        )
        assert plan["migration_id"] == "m1"
        assert plan["status"] == "planned"

        fetched = tmp_service.get_plan("m1")
        assert fetched["migration_id"] == "m1"

        listed = tmp_service.list_plans()
        assert any(p["migration_id"] == "m1" for p in listed)

    @pytest.mark.asyncio
    async def test_migrate_records_dry_run(self, tmp_path):
        mock_jsonapi = AsyncMock()
        service = MigrationService(storage_dir=tmp_path, jsonapi_client=mock_jsonapi)
        service.create_plan("m2", entities=["user--user"])

        result = await service.migrate_records(
            migration_id="m2",
            entity_type="user--user",
            records=[{"id": "42", "name": "alice", "mail": "a@example.com"}],
            dry_run=True,
        )

        assert result["processed"] == 1
        assert result["skipped"] == 1
        assert result["results"][0]["action"] == "would_create"
        mock_jsonapi.create_resource.assert_not_called()

    @pytest.mark.asyncio
    async def test_migrate_records_creates_and_updates(self, tmp_path):
        mock_jsonapi = AsyncMock()
        mock_jsonapi.create_resource.return_value = {"data": {"id": "uuid-1", "type": "user--user"}}
        mock_jsonapi.update_resource.return_value = {"data": {"id": "uuid-1", "type": "user--user"}}
        service = MigrationService(storage_dir=tmp_path, jsonapi_client=mock_jsonapi)
        service.create_plan("m3", entities=["user--user"])

        first = await service.migrate_records(
            "m3",
            "user--user",
            [{"id": "42", "name": "alice", "mail": "a@example.com"}],
        )
        second = await service.migrate_records(
            "m3",
            "user--user",
            [{"id": "42", "name": "alice2", "mail": "a@example.com"}],
        )

        assert first["created"] == 1
        assert second["updated"] == 1

    def test_tools_register(self, tmp_path):
        mock_jsonapi = AsyncMock()
        from drupal_mcp_server.services.migration_service import MigrationService

        service = MigrationService(storage_dir=tmp_path, jsonapi_client=mock_jsonapi)
        tools = _capture_tools(
            register_tools,
            jsonapi_client=mock_jsonapi,
            migration_service=service,
        )
        names = {tool.__name__ for tool in tools}
        assert "create_migration_plan" in names
        assert "migrate_records" in names
        assert "analyze_source_site" in names


class TestSchemaDrift:
    """Source and target schemas differ; the engine must adapt per record."""

    def test_sanitize_strips_computed_and_internal(self, tmp_path):
        attributes = {
            "title": "Hello",
            "body": {"value": "<p>x</p>", "format": "basic_html", "processed": "<p>x</p>", "summary": None},
            "drupal_internal__nid": 7,
            "changed": "2026-01-01",
        }
        service = MigrationService(storage_dir=tmp_path)
        clean = service._sanitize_attributes(attributes)
        assert "drupal_internal__nid" not in clean
        # Computed sub-props are removed but the writable value/format stay.
        assert set(clean["body"]) == {"value", "format"}
        # Audit timestamps are left to the adaptive retry, since they are
        # writable on nodes and worth preserving.
        assert clean["changed"] == "2026-01-01"
        assert clean["title"] == "Hello"

    @pytest.mark.asyncio
    async def test_drops_offending_attribute_and_retries(self, tmp_path):
        mock_jsonapi = AsyncMock()
        # First attempt: field does not exist. Second: succeeds.
        mock_jsonapi.create_resource.side_effect = [
            Exception(
                "Client error '422' — The attribute comment does not exist "
                "on the node--article resource type."
            ),
            {"data": {"id": "node-1", "type": "node--article"}},
        ]
        service = MigrationService(storage_dir=tmp_path, jsonapi_client=mock_jsonapi)
        service.create_plan("s1", entities=["node--article"])

        result = await service.migrate_records(
            "s1",
            "node--article",
            [{"id": "1", "title": "T", "comment": {"status": 2}}],
        )

        assert result["created"] == 1
        assert result["failed"] == 0
        # The retried payload no longer carries the offending attribute.
        retried_payload = mock_jsonapi.create_resource.call_args_list[1].args[1]
        assert "comment" not in retried_payload.get("attributes", {})

    @pytest.mark.asyncio
    async def test_drops_offending_relationship_and_retries(self, tmp_path):
        mock_jsonapi = AsyncMock()
        mock_jsonapi.create_resource.side_effect = [
            Exception(
                "Client error '422' — The attribute field_image does not exist "
                "on the node--article resource type."
            ),
            {"data": {"id": "node-1", "type": "node--article"}},
        ]
        service = MigrationService(storage_dir=tmp_path, jsonapi_client=mock_jsonapi)
        service.create_plan("s2", entities=["node--article"])

        result = await service.migrate_records(
            "s2",
            "node--article",
            [
                {
                    "id": "1",
                    "attributes": {"title": "T"},
                    "relationships": {"field_image": {"data": None}},
                }
            ],
        )

        assert result["created"] == 1
        retried_payload = mock_jsonapi.create_resource.call_args_list[1].args[1]
        assert "field_image" not in retried_payload.get("relationships", {})

    @pytest.mark.asyncio
    async def test_gives_up_when_nothing_actionable(self, tmp_path):
        mock_jsonapi = AsyncMock()
        mock_jsonapi.create_resource.side_effect = Exception("Client error '500' — boom")
        service = MigrationService(storage_dir=tmp_path, jsonapi_client=mock_jsonapi)
        service.create_plan("s3", entities=["node--article"])

        result = await service.migrate_records(
            "s3", "node--article", [{"id": "1", "title": "T"}]
        )

        assert result["failed"] == 1
        # A single attempt: the error named no field to drop.
        assert mock_jsonapi.create_resource.call_count == 1


class TestRelationshipMapping:
    """Relationships must be remapped, or dropped when unresolvable."""

    def test_bundle_and_revision_relationships_are_dropped(self):
        relationships = {
            "node_type": {"data": {"type": "node_type--node_type", "id": "src-uuid"}},
            "revision_uid": {"data": {"type": "user--user", "id": "src-user"}},
            "uid": {"data": {"type": "user--user", "id": "src-user"}},
        }
        plan = {
            "state": {
                "entities": {
                    "user--user": {"records": {"src-user": "target-user"}},
                }
            }
        }
        mapped = MigrationService._map_relationships(relationships, plan)
        # Bundle pointer and revision bookkeeping are gone; the author is
        # remapped to the target UUID.
        assert "node_type" not in mapped
        assert "revision_uid" not in mapped
        assert mapped["uid"]["data"] == {"type": "user--user", "id": "target-user"}

    def test_unmappable_and_virtual_references_are_dropped(self):
        relationships = {
            "field_tags": {"data": [{"type": "taxonomy_term--tags", "id": "not-migrated"}]},
            "parent": {"data": [{"type": "taxonomy_term--departures", "id": "virtual"}]},
            "field_image": {"data": None},
        }
        plan = {"state": {"entities": {}}}
        mapped = MigrationService._map_relationships(relationships, plan)
        # Unmappable source UUIDs would 404 on the target, so they are
        # dropped; the explicit null (clear the field) is preserved.
        assert "field_tags" not in mapped
        assert "parent" not in mapped
        assert mapped["field_image"]["data"] is None

    def test_empty_relationship_list_is_preserved(self):
        relationships = {"field_tags": {"data": []}}
        mapped = MigrationService._map_relationships(relationships, {"state": {"entities": {}}})
        assert mapped["field_tags"]["data"] == []