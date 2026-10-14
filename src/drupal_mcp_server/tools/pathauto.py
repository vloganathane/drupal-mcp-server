"""Pathauto and Redirect pattern tools for Drupal."""

from typing import Any

from fastmcp import FastMCP

from ._utils import ensure_dict as _ensure_dict
from ._utils import langcode_field as _langcode_field


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")
    jsonapi = deps.get("jsonapi_client")

    @mcp.tool()
    async def pathauto_pattern_list(
        entity_type: str | None = None,
        bundle: str | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List pathauto patterns.

        A pattern's target entity type and bundle are encoded in its *id*, as
        `{entity_type}--{bundle}`, rather than held in fields of their own.
        `filter[entity_type]` and `filter[bundle]` therefore answered 400 "the
        field ... does not exist" on every call. Both are needed to filter
        server-side; with only one there is no field to match on, so every
        pattern is returned and the caller narrows from the ids.
        """
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if entity_type and bundle:
                params["filter[id]"] = f"{entity_type}--{bundle}"
            
            result = await jsonapi.get_resource("pathauto_pattern", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def pathauto_pattern_get(
        pattern_id: str,
        include: str = "",
    ) -> dict[str, Any]:
        """Get a single pathauto pattern by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("pathauto_pattern", pattern_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def pathauto_pattern_create(
        id: str,
        label: str,
        entity_type: str,
        bundle: str,
        pattern: str,
        weight: int = 0,
        langcode: str | None = None,
    ) -> dict[str, Any]:
        """Create a new pathauto pattern."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            pattern_data = {
                "type": "pathauto_pattern",
                "id": id,
                "label": label,
                "entity_type": entity_type,
                "bundle": bundle,
                "pattern": pattern,
                "weight": weight,
                **_langcode_field(langcode),
            }
            
            result = await jsonapi.create_resource("pathauto_pattern", pattern_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def pathauto_pattern_update(
        pattern_id: str,
        label: str | None = None,
        pattern: str | None = None,
        weight: int | None = None,
    ) -> dict[str, Any]:
        """Update a pathauto pattern."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            current = await jsonapi.get_by_id("pathauto_pattern", pattern_id)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data: dict[str, Any] = {"id": pattern_id, "type": "pathauto_pattern"}
            if label is not None:
                update_data["label"] = label
            if pattern is not None:
                update_data["pattern"] = pattern
            if weight is not None:
                update_data["weight"] = weight
            
            result = await jsonapi.update_resource("pathauto_pattern", pattern_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def pathauto_pattern_delete(
        pattern_id: str,
    ) -> dict[str, Any]:
        """Delete a pathauto pattern."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.delete_resource("pathauto_pattern", pattern_id)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def pathauto_generate(
        entity_type: str | None = None,
        bundle: str | None = None,
        count: int = 100,
    ) -> dict[str, Any]:
        """Generate pathauto aliases."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["pathauto:generate"]
            if entity_type:
                cmd.extend(["--entity-type", entity_type])
            if bundle:
                cmd.extend(["--bundle", bundle])
            cmd.extend(["--count", str(count)])
            result = await drush.run(*cmd)
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def pathauto_token_list(
        entity_type: str | None = None,
    ) -> dict[str, Any]:
        """List available pathauto tokens."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["token:list"]
            if entity_type:
                cmd.append(entity_type)
            result = await drush.run(*cmd)
            return _ensure_dict({"tokens": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def redirect_pattern_list(
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List redirect patterns."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            result = await jsonapi.get_resource("redirect", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    # NOTE: `redirect_bulk_create` is registered by `redirects.py` — do not
    # duplicate it here or FastMCP will warn about a conflicting component.
