"""Fields management tools for Drupal."""

from typing import Any

from fastmcp import FastMCP


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    jsonapi = deps.get("jsonapi_client")

    def _ensure_dict(result: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
        """Ensure result is a dict, not a list."""
        if result is None:
            return {"error": "No response"}
        if isinstance(result, list):
            return {"error": f"Unexpected list response: {result}"}
        return result

    @mcp.tool()
    async def field_config_list(
        filters: dict[str, Any] | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List all field configurations on a Drupal site."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if filters:
                for key, value in filters.items():
                    params[f"filter[{key}]"] = str(value)
            
            result = await jsonapi.get_resource("field_config", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def field_config_get(config_id: str, include: str = "") -> dict[str, Any]:
        """Get a single field configuration by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("field_config", config_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def field_config_create(
        field_name: str,
        field_type: str,
        entity_type: str,
        bundle: str,
        label: str,
        description: str = "",
        required: bool = False,
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new field configuration."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            config_id = f"{entity_type}.{bundle}.{field_name}"
            field_data = {
                "type": "field_config",
                "id": config_id,
                "field_name": field_name,
                "field_type": field_type,
                "entity_type": entity_type,
                "bundle": bundle,
                "label": label,
                "description": description,
                "required": required,
                "settings": settings or {},
            }
            
            result = await jsonapi.create_resource("field_config", field_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def field_config_update(
        config_id: str,
        label: str | None = None,
        description: str | None = None,
        required: bool | None = None,
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update a field configuration."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            # Get current config to preserve existing config
            current = await jsonapi.get_by_id("field_config", config_id)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data: dict[str, Any] = {"id": config_id, "type": "field_config"}
            if label is not None:
                update_data["label"] = label
            if description is not None:
                update_data["description"] = description
            if required is not None:
                update_data["required"] = required
            if settings is not None:
                update_data["settings"] = settings
            
            result = await jsonapi.update_resource("field_config", config_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def field_config_delete(config_id: str) -> dict[str, Any]:
        """Delete a field configuration."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.delete_resource("field_config", config_id)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def field_storage_list(
        filters: dict[str, Any] | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List all field storage configurations on a Drupal site."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if filters:
                for key, value in filters.items():
                    params[f"filter[{key}]"] = str(value)
            
            result = await jsonapi.get_resource("field_storage_config", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def field_storage_get(config_id: str, include: str = "") -> dict[str, Any]:
        """Get a single field storage configuration by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("field_storage_config", config_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def field_storage_create(
        field_name: str,
        field_type: str,
        label: str,
        description: str = "",
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new field storage configuration."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            field_data = {
                "type": "field_storage_config",
                "id": field_name,
                "field_name": field_name,
                "field_type": field_type,
                "label": label,
                "description": description,
                "settings": settings or {},
            }
            
            result = await jsonapi.create_resource("field_storage_config", field_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def field_storage_update(
        config_id: str,
        label: str | None = None,
        description: str | None = None,
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update a field storage configuration."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            # Get current config to preserve existing config
            current = await jsonapi.get_by_id("field_storage_config", config_id)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data: dict[str, Any] = {"id": config_id, "type": "field_storage_config"}
            if label is not None:
                update_data["label"] = label
            if description is not None:
                update_data["description"] = description
            if settings is not None:
                update_data["settings"] = settings
            
            result = await jsonapi.update_resource("field_storage_config", config_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def field_storage_delete(config_id: str) -> dict[str, Any]:
        """Delete a field storage configuration."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.delete_resource("field_storage_config", config_id)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}
