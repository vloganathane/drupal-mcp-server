"""Tests for migration plan helpers and service."""

import tempfile
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