"""Search API integration tools for Drupal."""

import os
import yaml
from typing import Any

from fastmcp import FastMCP


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")
    jsonapi = deps.get("jsonapi_client")

    def _ensure_dict(result: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
        """Ensure result is a dict, not a list."""
        if result is None:
            return {"error": "No response"}
        if isinstance(result, list):
            return {"error": f"Unexpected list response: {result}"}
        return result

    @mcp.tool()
    async def search_api_server_list(
        filters: dict[str, Any] | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List all Search API servers."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params: dict[str, Any] = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if filters:
                for key, value in filters.items():
                    params[f"filter[{key}]"] = str(value)
            
            result = await jsonapi.get_resource("search_api_server", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def search_api_server_get(
        server_id: str,
        include: str = "",
    ) -> dict[str, Any]:
        """Get a single Search API server by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params: dict[str, Any] = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("search_api_server", server_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def search_api_server_create(
        id: str,
        label: str,
        backend: str = "database",
        backend_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new Search API server."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            server_data: dict[str, Any] = {
                "type": "search_api_server",
                "id": id,
                "label": label,
                "backend": backend,
            }
            if backend_config:
                server_data["backend_config"] = backend_config
            
            result = await jsonapi.create_resource("search_api_server", server_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def search_api_index_list(
        server_id: str | None = None,
        filters: dict[str, Any] | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List Search API indexes."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params: dict[str, Any] = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if server_id:
                params["filter[server]"] = server_id
            if filters:
                for key, value in filters.items():
                    params[f"filter[{key}]"] = str(value)
            
            result = await jsonapi.get_resource("search_api_index", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def search_api_index_get(
        index_id: str,
        include: str = "",
    ) -> dict[str, Any]:
        """Get a single Search API index by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params: dict[str, Any] = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("search_api_index", index_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def search_api_index_create(
        id: str,
        label: str,
        server_id: str,
        datasource: str,
        datasource_settings: dict[str, Any] | None = None,
        processors: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create a new Search API index."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            index_data: dict[str, Any] = {
                "type": "search_api_index",
                "id": id,
                "label": label,
                "server": server_id,
                "datasource": datasource,
            }
            if datasource_settings:
                index_data["datasource_settings"] = datasource_settings
            if processors:
                index_data["processors"] = processors
            
            result = await jsonapi.create_resource("search_api_index", index_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def search_api_index_update(
        index_id: str,
        label: str | None = None,
        status: str | None = None,
        processors: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Update a Search API index."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            current = await jsonapi.get_by_id("search_api_index", index_id)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data: dict[str, Any] = {"id": index_id, "type": "search_api_index"}
            if label is not None:
                update_data["label"] = label
            if status is not None:
                update_data["status"] = status
            if processors is not None:
                update_data["processors"] = processors
            
            result = await jsonapi.update_resource("search_api_index", index_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def search_api_index_reindex(
        index_id: str,
        batch_size: int = 100,
    ) -> dict[str, Any]:
        """Trigger reindexing of a Search API index."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("search-api:index", [index_id, "--batch-size", str(batch_size)])
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def search_api_index_clear(
        index_id: str,
    ) -> dict[str, Any]:
        """Clear a Search API index."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("search-api:clear", [index_id])
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def search_api_server_enable(
        server_id: str,
    ) -> dict[str, Any]:
        """Enable a Search API server."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("config:set", ["search_api.server." + server_id, "status", "true"])
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def search_api_server_disable(
        server_id: str,
    ) -> dict[str, Any]:
        """Disable a Search API server."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("config:set", ["search_api.server." + server_id, "status", "false"])
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def search_api_facet_list(
        index_id: str | None = None,
        page_limit: int = 50,
    ) -> dict[str, Any]:
        """List Search API facets."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params: dict[str, Any] = {"page[limit]": "50"}
            
            if index_id:
                params["filter[index]"] = index_id
            
            result = await jsonapi.get_resource("search_api_facet", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def search_api_facet_create(
        id: str,
        label: str,
        index_id: str,
        field: str,
        facet_type: str = "search_api_facet",
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a Search API facet."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            facet_data: dict[str, Any] = {
                "type": "search_api_facet",
                "id": id,
                "label": label,
                "index": index_id,
                "field_identifier": field,
            }
            if settings:
                facet_data["settings"] = settings
            
            result = await jsonapi.create_resource("search_api_facet", facet_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}
