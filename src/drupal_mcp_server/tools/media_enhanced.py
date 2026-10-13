"""Media enhancement tools for Drupal."""

import os
import yaml
import base64
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
    async def media_type_list(
        filters: dict[str, Any] | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List all media types."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if filters:
                for key, value in filters.items():
                    params[f"filter[{key}]"] = str(value)
            
            result = await jsonapi.get_resource("media_type", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def media_type_get(
        media_type_id: str,
        include: str = "",
    ) -> dict[str, Any]:
        """Get a single media type by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("media_type", media_type_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def media_type_create(
        id: str,
        label: str,
        description: str = "",
        source: str = "file",
        source_configuration: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new media type."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            media_type_data: dict[str, Any] = {
                "type": "media_type",
                "id": id,
                "label": label,
                "description": description,
                "source": source,
            }
            if source_configuration:
                media_type_data["source_configuration"] = source_configuration
            
            result = await jsonapi.create_resource("media_type", media_type_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def media_create_from_url(
        url: str,
        media_type: str,
        name: str | None = None,
        field_name: str = "field_media_oembed_video",
    ) -> dict[str, Any]:
        """Create media from URL (oEmbed)."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            media_data = {
                "type": f"media--{media_type}",
                field_name: url,
            }
            if name:
                media_data["name"] = name
            
            result = await jsonapi.create_resource(f"media--{media_type}", media_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def media_create_from_base64(
        base64_data: str,
        filename: str,
        media_type: str = "file",
        name: str | None = None,
        mime_type: str | None = None,
    ) -> dict[str, Any]:
        """Create media from base64 encoded file data."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            # Save base64 to temp file and import via drush
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as tmp:
                tmp.write(base64.b64decode(base64_data))
                tmp_path = tmp.name
            
            result = await drush.run("media:import", [tmp_path, "--type", media_type])
            os.unlink(tmp_path)
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def media_derivative_generate(
        media_id: str,
        derivative_id: str,
    ) -> dict[str, Any]:
        """Generate a specific derivative for media."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("media:derivative:generate", [media_id, derivative_id])
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def media_bulk_import(
        source_dir: str,
        media_type: str = "file",
        recursive: bool = True,
    ) -> dict[str, Any]:
        """Bulk import media files from directory."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["media:import", source_dir, "--type", media_type]
            if recursive:
                cmd.append("--recursive")
            result = await drush.run(*cmd)
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def media_library_list(
        filters: dict[str, Any] | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List media library items."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if filters:
                for key, value in filters.items():
                    params[f"filter[{key}]"] = str(value)
            
            result = await jsonapi.get_resource("media", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}
