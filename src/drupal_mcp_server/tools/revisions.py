"""Revisions management tools for Drupal."""

from typing import Any

from fastmcp import FastMCP

from ._utils import ensure_dict as _ensure_dict


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    jsonapi = deps.get("jsonapi_client")

    @mcp.tool()
    async def revision_list(
        entity_type: str,
        entity_id: str,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List all revisions for an entity."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            # Revisions are typically accessed via entity-specific endpoints
            # e.g., /jsonapi/node/article/{uuid}/revisions
            resource_type = f"{entity_type}--{entity_type}"
            result = await jsonapi.get_resource(f"{resource_type}/{entity_id}/revisions", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def revision_get(
        entity_type: str,
        entity_id: str,
        revision_id: str,
        include: str = "",
    ) -> dict[str, Any]:
        """Get a specific revision of an entity."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            
            resource_type = f"{entity_type}--{entity_type}"
            result = await jsonapi.get_by_id(f"{resource_type}/{entity_id}/revisions", revision_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def revision_revert(
        entity_type: str,
        entity_id: str,
        revision_id: str,
    ) -> dict[str, Any]:
        """Revert an entity to a specific revision."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            # Get the revision data
            resource_type = f"{entity_type}--{entity_type}"
            revision = await jsonapi.get_by_id(f"{resource_type}/{entity_id}/revisions", revision_id)
            revision = _ensure_dict(revision)
            if revision.get("error"):
                return revision
            
            # Extract revision data and apply to entity
            revision_data = revision.get("data", {})
            attributes = revision_data.get("attributes", {})
            
            # Update entity with revision data
            update_data = {
                "id": entity_id,
                "type": f"{entity_type}--{entity_type}",
            }
            update_data.update(attributes)
            
            result = await jsonapi.update_resource(f"{entity_type}--{entity_type}", entity_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def revision_delete(
        entity_type: str,
        entity_id: str,
        revision_id: str,
    ) -> dict[str, Any]:
        """Delete a specific revision of an entity."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            resource_type = f"{entity_type}--{entity_type}"
            result = await jsonapi.delete_resource(f"{resource_type}/{entity_id}/revisions", revision_id)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def revision_diff(
        entity_type: str,
        entity_id: str,
        revision_id_1: str,
        revision_id_2: str,
    ) -> dict[str, Any]:
        """Diff two revisions of an entity."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            
            resource_type = f"{entity_type}--{entity_type}"
            
            # Get both revisions
            rev1 = await jsonapi.get_by_id(f"{resource_type}/{entity_id}/revisions", revision_id_1)
            rev1 = _ensure_dict(rev1)
            if rev1.get("error"):
                return rev1
            
            rev2 = await jsonapi.get_by_id(f"{resource_type}/{entity_id}/revisions", revision_id_2)
            rev2 = _ensure_dict(rev2)
            if rev2.get("error"):
                return rev2
            
            # Extract attributes
            attrs1 = rev1.get("data", {}).get("attributes", {})
            attrs2 = rev2.get("data", {}).get("attributes", {})
            
            # Simple diff
            all_keys = set(attrs1.keys()) | set(attrs2.keys())
            diff = []
            
            for key in sorted(all_keys):
                val1 = attrs1.get(key)
                val2 = attrs2.get(key)
                if val1 != val2:
                    diff.append({
                        "field": key,
                        "from": val1,
                        "to": val2,
                    })
            
            return {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "revision_1": revision_id_1,
                "revision_2": revision_id_2,
                "differences": diff,
                "has_changes": len(diff) > 0,
            }
        except Exception as e:
            return {"error": str(e)}
