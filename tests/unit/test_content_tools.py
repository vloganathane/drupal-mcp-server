"""Functional tests for content management tools with mocked responses."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_jsonapi():
    client = AsyncMock()
    return client


@pytest.fixture
def mock_drush():
    client = AsyncMock()
    return client


@pytest.fixture
def mock_ai():
    service = AsyncMock()
    return service


def _capture_tools(register_func, **deps):
    """Capture all tool functions registered by a register_tools function."""
    mock_mcp = MagicMock()
    registered_tools = []

    def tool_decorator():
        def wrapper(f):
            registered_tools.append(f)
            return f
        return wrapper

    mock_mcp.tool = MagicMock(side_effect=tool_decorator)
    register_func(mock_mcp, **deps)
    return registered_tools


def _find_tool(registered_tools, name):
    """Find a registered tool by function name."""
    for tool in registered_tools:
        if tool.__name__ == name:
            return tool
    raise ValueError(f"Tool {name} not found among {len(registered_tools)} registered tools")


class TestCreateNode:
    """Tests for create_node tool."""

    @pytest.mark.asyncio
    async def test_create_node_success(self, mock_jsonapi):
        from drupal_mcp_server.tools.content import register_tools

        tools = _capture_tools(register_tools, jsonapi_client=mock_jsonapi)
        create_node = _find_tool(tools, "create_node")

        mock_jsonapi.create_resource.return_value = {
            "data": {"id": "test-uuid", "type": "node--article", "attributes": {"title": "Test"}}
        }

        result = await create_node(bundle="article", fields={"title": "Test Article"})

        assert "error" not in result
        assert result["data"]["attributes"]["title"] == "Test"
        # Tool sets type field from bundle when not provided
        call_args = mock_jsonapi.create_resource.call_args
        assert call_args[0][0] == "node--article"

    @pytest.mark.asyncio
    async def test_create_node_requires_title(self, mock_jsonapi):
        from drupal_mcp_server.tools.content import register_tools

        tools = _capture_tools(register_tools, jsonapi_client=mock_jsonapi)
        create_node = _find_tool(tools, "create_node")

        result = await create_node(bundle="article", fields={})

        assert result == {"error": "title is required"}

    @pytest.mark.asyncio
    async def test_create_node_no_client(self):
        from drupal_mcp_server.tools.content import register_tools

        tools = _capture_tools(register_tools, jsonapi_client=None)
        create_node = _find_tool(tools, "create_node")

        result = await create_node(bundle="article", fields={"title": "Test"})

        assert result == {"error": "JSON:API not available"}


class TestQueryNodes:
    """Tests for query_nodes tool."""

    @pytest.mark.asyncio
    async def test_query_nodes_with_pagination(self, mock_jsonapi):
        from drupal_mcp_server.tools.content import register_tools

        tools = _capture_tools(register_tools, jsonapi_client=mock_jsonapi)
        query_nodes = _find_tool(tools, "query_nodes")

        mock_jsonapi.get_resource.return_value = {
            "data": [{"id": "1", "type": "node--article"}],
            "meta": {"count": 1},
        }

        result = await query_nodes(bundle="article", page_limit=10, page_offset=0)

        assert "error" not in result
        mock_jsonapi.get_resource.assert_called_once()
        call_args = mock_jsonapi.get_resource.call_args
        assert call_args[0][0] == "node--article"

    @pytest.mark.asyncio
    async def test_query_nodes_invalid_pagination(self, mock_jsonapi):
        from drupal_mcp_server.tools.content import register_tools

        tools = _capture_tools(register_tools, jsonapi_client=mock_jsonapi)
        query_nodes = _find_tool(tools, "query_nodes")

        result = await query_nodes(bundle="article", page_limit=-1)

        assert "error" in result


class TestUploadMedia:
    """Tests for upload_media tool."""

    @pytest.mark.asyncio
    async def test_upload_media_file_not_found(self, mock_jsonapi):
        from drupal_mcp_server.tools.content import register_tools

        tools = _capture_tools(register_tools, jsonapi_client=mock_jsonapi)
        upload_media = _find_tool(tools, "upload_media")

        result = await upload_media(file_path="/nonexistent/file.jpg")

        assert "error" in result
        assert "File not found" in result["error"]

    @pytest.mark.asyncio
    async def test_upload_media_path_traversal(self, mock_jsonapi):
        from drupal_mcp_server.tools.content import register_tools

        tools = _capture_tools(register_tools, jsonapi_client=mock_jsonapi)
        upload_media = _find_tool(tools, "upload_media")

        # Use a path that exists but is not a regular file
        result = await upload_media(file_path="/etc")

        assert "error" in result
