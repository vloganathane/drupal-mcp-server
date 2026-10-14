"""Layout Builder and Block management tools for Drupal."""

from typing import Any

from fastmcp import FastMCP

from ._utils import ensure_dict as _ensure_dict

# JSON:API has never exposed a `layout_builder` resource. Every tool below
# used to request one and come back with a 404 whose only clue was the URL.
_LAYOUT_EXPLANATION = (
    "Layout Builder does not expose a JSON:API resource, so layouts cannot be "
    "read or written over JSON:API at all. The bundle-level display, including "
    "whether Layout Builder is enabled for it, is available from "
    "`entity_view_display`; per-entity overrides live only in each entity's "
    "`layout_builder__overrides` field. To edit layouts through HTTP, enable "
    "the Layout Builder REST resource (module `rest` + resource type "
    "`layout_builder`) or use drush config commands against "
    "`core.entity_view_display.*`."
)


def _layout_unavailable(entity_type: str, bundle: str) -> dict[str, Any]:
    return {
        "error": _LAYOUT_EXPLANATION,
        "entity_type": entity_type,
        "bundle": bundle,
    }


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")
    jsonapi = deps.get("jsonapi_client")

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
        """Report which entity view displays have Layout Builder enabled.

        Layouts themselves are not readable over JSON:API (see the other
        layout_builder_* tools), but the display config that switches Layout
        Builder on for a bundle is, so this returns that instead of a 404.
        """
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params: dict[str, Any] = {"filter[targetEntityType]": entity_type}
            if bundle:
                params["filter[bundle]"] = bundle
            result = await jsonapi.get_resource("entity_view_display", params)
        except Exception as e:
            return {"error": str(e)}

        rows = (result.get("data") or []) if isinstance(result, dict) else []
        displays = []
        for row in rows:
            attrs = row.get("attributes", {}) if isinstance(row, dict) else {}
            config = attrs.get("config", {}) or {}
            displays.append({
                "id": attrs.get("id") or row.get("id"),
                "entity_type": attrs.get("targetEntityType") or attrs.get("entity_type"),
                "bundle": attrs.get("bundle"),
                "view_mode": attrs.get("mode"),
                "layout_builder_enabled": bool(
                    config.get("layout_builder__enabled")
                    or attrs.get("layout_builder__enabled")
                ),
                "section_count": len(
                    config.get("layout_builder__sections")
                    or attrs.get("layout_builder__sections")
                    or []
                ),
            })
        return _ensure_dict({
            "entity_type": entity_type,
            "bundle": bundle,
            "displays": displays,
            "note": (
                "These are entity view displays. Layout Builder stores its "
                "sections inside them, so the section bodies are not exposed "
                "separately over JSON:API."
            ),
        })

    @mcp.tool()
    async def layout_builder_get(
        entity_type: str,
        bundle: str,
    ) -> dict[str, Any]:
        """Get Layout Builder configuration for entity type/bundle."""
        return _layout_unavailable(entity_type, bundle)

    @mcp.tool()
    async def layout_builder_create(
        entity_type: str,
        bundle: str,
        layout: dict[str, Any],
        lock: bool = False,
    ) -> dict[str, Any]:
        """Create or update Layout Builder configuration."""
        return _layout_unavailable(entity_type, bundle)

    @mcp.tool()
    async def layout_builder_update(
        entity_type: str,
        bundle: str,
        layout: dict[str, Any] | None = None,
        lock: bool | None = None,
    ) -> dict[str, Any]:
        """Update Layout Builder configuration."""
        return _layout_unavailable(entity_type, bundle)

    @mcp.tool()
    async def layout_builder_sections_list(
        entity_type: str,
        bundle: str,
    ) -> dict[str, Any]:
        """List sections in a Layout Builder layout."""
        return _layout_unavailable(entity_type, bundle)

    @mcp.tool()
    async def layout_builder_section_add(
        entity_type: str,
        bundle: str,
        section: dict[str, Any],
    ) -> dict[str, Any]:
        """Add a section to Layout Builder layout."""
        return _layout_unavailable(entity_type, bundle)

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
        return _layout_unavailable(entity_type, bundle)
