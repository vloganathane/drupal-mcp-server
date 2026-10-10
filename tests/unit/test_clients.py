"""Unit tests for HTTP clients."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_jsonapi_client_get_resource():
    from drupal_mcp_server.clients import JSONAPIClient
    settings = MagicMock()
    settings.DRUPAL_BASE_URL = "http://localhost"
    settings.DRUPAL_JSONAPI_PATH = "/jsonapi"
    
    client = JSONAPIClient(settings)
    
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MagicMock(
            json=lambda: {"data": []},
            raise_for_status=lambda: None,
        )
        result = await client.get_resource("node--article")
        assert "data" in result


@pytest.mark.asyncio
async def test_graphql_client_execute():
    from drupal_mcp_server.clients import GraphQLClient
    settings = MagicMock()
    settings.DRUPAL_BASE_URL = "http://localhost"
    settings.DRUPAL_GRAPHQL_PATH = "/graphql"
    
    client = GraphQLClient(settings)
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MagicMock(
            json=lambda: {"data": {"node": {}}},
            raise_for_status=lambda: None,
        )
        result = await client.execute("{ node { title } }")
        assert "data" in result


@pytest.mark.asyncio
async def test_drush_client_run():
    from drupal_mcp_server.clients import DrushClient
    settings = MagicMock()
    settings.DRUSH_PATH = "drush"
    settings.DRUSH_ALIAS = "@self"
    
    client = DrushClient(settings)
    result = await client.run("status")
    assert "returncode" in result
