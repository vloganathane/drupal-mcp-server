"""Layout Builder and Block management tools for Drupal."""

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
    async def block_list(
        filters: dict[str, Any] | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List all blocks."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if filters:
                for key, value in filters.items():
                    params[f"filter[{key}]"] = str(value)
            
            result = await jsonapi.get_resource("block", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def block_get(
        block_id: str,
        include: str = "",
    ) -> dict[str, Any]:
        """Get a single block by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("block", block_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def block_create(
        id: str,
        label: str,
        plugin: str,
        region: str | None = None,
        settings: dict[str, Any] | None = None,
        visibility: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new block."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            block_data: dict[str, Any] = {
                "type": "block",
                "id": id,
                "label": label,
                "plugin": plugin,
            }
            if region:
                block_data["region"] = region
            if settings:
                block_data["settings"] = settings
            if visibility:
                block_data["visibility"] = visibility
            
            result = await jsonapi.create_resource("block", block_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def block_update(
        block_id: str,
        label: str | None = None,
        region: str | None = None,
        settings: dict[str, Any] | None = None,
        visibility: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update a block."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            current = await jsonapi.get_by_id("block", block_id)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data: dict[str, Any] = {"id": block_id, "type": "block"}
            if label is not None:
                update_data["label"] = label
            if region is not None:
                update_data["region"] = region
            if settings is not None:
                update_data["settings"] = settings
            if visibility is not None:
                update_data["visibility"] = visibility
            
            result = await jsonapi.update_resource("block", block_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def block_delete(
        block_id: str,
    ) -> dict[str, Any]:
        """Delete a block."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.delete_resource("block", block_id)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def block_place(
        block_id: str,
        region: str,
        weight: int = 0,
    ) -> dict[str, Any]:
        """Place a block in a region with weight."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            current = await jsonapi.get_by_id("block", block_id)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data = {
                "id": block_id,
                "type": "block",
                "region": region,
                "weight": weight,
            }
            
            result = await jsonapi.update_resource("block", block_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def layout_builder_list(
        entity_type: str = "node",
        bundle: str | None = None,
    ) -> dict[str, Any]:
        """List Layout Builder configurations for an entity type/bundle."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if bundle:
                params["filter[bundle]"] = bundle
            
            result = await jsonapi.get_resource("layout_builder", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def layout_builder_get(
        entity_type: str,
        bundle: str,
    ) -> dict[str, Any]:
        """Get Layout Builder configuration for entity type/bundle."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.get_by_id("layout_builder", f"{entity_type}.{bundle}")
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def layout_builder_create(
        entity_type: str,
        bundle: str,
        layout: dict[str, Any],
        lock: bool = False,
    ) -> dict[str, Any]:
        """Create or update Layout Builder configuration."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            layout_data = {
                "type": "layout_builder",
                "id": f"{entity_type}.{bundle}",
                "entity_type": entity_type,
                "bundle": bundle,
                "layout": layout,
                "lock": lock,
            }
            
            result = await jsonapi.create_resource("layout_builder", layout_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def layout_builder_update(
        entity_type: str,
        bundle: str,
        layout: dict[str, Any] | None = None,
        lock: bool | None = None,
    ) -> dict[str, Any]:
        """Update Layout Builder configuration."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            layout_id = f"{entity_type}.{bundle}"
            current = await jsonapi.get_by_id("layout_builder", layout_id)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data: dict[str, Any] = {"id": layout_id, "type": "layout_builder"}
            if layout is not None:
                update_data["layout"] = layout
            if lock is not None:
                update_data["lock"] = lock
            
            result = await jsonapi.update_resource("layout_builder", layout_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def layout_builder_sections_list(
        entity_type: str,
        bundle: str,
    ) -> dict[str, Any]:
        """List sections in a Layout Builder layout."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            layout_id = f"{entity_type}.{bundle}"
            layout = await jsonapi.get_by_id("layout_builder", layout_id)
            layout = _ensure_dict(layout)
            if layout.get("error"):
                return layout
            
            sections = layout.get("data", {}).get("attributes", {}).get("layout", {})
            return _ensure_dict({"sections": sections})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def layout_builder_section_add(
        entity_type: str,
        bundle: str,
        section: dict[str, Any],
    ) -> dict[str, Any]:
        """Add a section to Layout Builder layout."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            layout_id = f"{entity_type}.{bundle}"
            layout = await jsonapi.get_by_id("layout_builder", layout_id)
            layout = _ensure_dict(layout)
            if layout.get("error"):
                return layout
            
            sections = layout.get("data", {}).get("attributes", {}).get("layout", {})
            section_id = f"section_{len(sections) + 1}"
            sections[section_id] = section
            
            return await layout_builder_update(entity_type, bundle, {"layout": sections})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def block_plugin_list(
        filters: dict[str, Any] | None = None,
        page_limit: int = 50,
    ) -> dict[str, Any]:
        """List available block plugins."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("ev", [
                "exec(\"print_r(array_keys(\\Drupal::service('plugin.manager.block')->getDefinitions()));\", \\$output); print_r(\\$output);"
            ])
            return _ensure_dict({"block_plugins": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def block_region_list(
        theme: str | None = None,
    ) -> dict[str, Any]:
        """List available regions for a theme."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            theme_arg = f"--theme={theme}" if theme else ""
            result = await drush.run("ev", [
                "exec(\"\\$theme = \\Drupal::service('theme.registry')->get('" + (theme or "bartik") + "'); print_r(array_keys(\\$theme->getRegions()));\", \\$output); print_r(\\$output);"
            ])
            return _ensure_dict({"regions": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def layout_builder_override_remove(
        entity_type: str,
        bundle: str,
    ) -> dict[str, Any]:
        """Remove Layout Builder override (revert to default)."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            layout_id = f"{entity_type}.{bundle}"
            result = await jsonapi.delete_resource("layout_builder", layout_id)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}
