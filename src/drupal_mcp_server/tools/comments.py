"""Comments tools for Drupal."""

from typing import Any

from fastmcp import FastMCP

from ._utils import ensure_dict as _ensure_dict


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")
    jsonapi = deps.get("jsonapi_client")

    @mcp.tool()
    async def comment_list(
        entity_type: str | None = None,
        entity_id: str | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List comments."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if entity_type:
                params["filter[entity_type]"] = entity_type
            if entity_id:
                params["filter[entity_id]"] = entity_id
            
            result = await jsonapi.get_resource("comment", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def comment_get(
        comment_id: str,
        include: str = "",
    ) -> dict[str, Any]:
        """Get a single comment by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("comment", comment_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def comment_create(
        entity_type: str,
        entity_id: str,
        subject: str,
        body: str,
        field_name: str = "comment",
        pid: int = 0,
        uid: int | None = None,
    ) -> dict[str, Any]:
        """Create a new comment."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            comment_data = {
                "type": "comment",
                "entity_type": entity_type,
                "entity_id": entity_id,
                "field_name": field_name,
                "subject": subject,
                "comment_body": {"value": body, "format": "basic_html"},
                "pid": pid,
            }
            if uid is not None:
                comment_data["uid"] = uid
            
            result = await jsonapi.create_resource("comment", comment_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def comment_update(
        comment_id: str,
        subject: str | None = None,
        body: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Update a comment."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            current = await jsonapi.get_by_id("comment", comment_id)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data: dict[str, Any] = {"id": comment_id, "type": "comment"}
            if subject is not None:
                update_data["subject"] = subject
            if body is not None:
                update_data["comment_body"] = {"value": body, "format": "basic_html"}
            if status is not None:
                update_data["status"] = status
            
            result = await jsonapi.update_resource("comment", comment_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def comment_delete(
        comment_id: str,
    ) -> dict[str, Any]:
        """Delete a comment."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.delete_resource("comment", comment_id)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def comment_thread_list(
        entity_type: str,
        entity_id: str,
        field_name: str = "comment",
    ) -> dict[str, Any]:
        """List comment thread for an entity."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {
                "filter[entity_type]": entity_type,
                "filter[entity_id]": entity_id,
                "filter[field_name]": field_name,
                "filter[pid]": "0",
                "page[limit]": "50",
            }
            result = await jsonapi.get_resource("comment", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def comment_approve(
        comment_id: str,
    ) -> dict[str, Any]:
        """Approve a comment (set status to published)."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            return await comment_update(comment_id, status="published")
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def comment_unapprove(
        comment_id: str,
    ) -> dict[str, Any]:
        """Unapprove a comment (set status to unpublished)."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            return await comment_update(comment_id, status="unpublished")
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def comment_field_settings(
        entity_type: str,
        bundle: str,
        field_name: str = "comment",
    ) -> dict[str, Any]:
        """Get comment field settings for entity type/bundle."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["config:get", f"field.field.{entity_type}.{bundle}.{field_name}"]
            result = await drush.run(*cmd)
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def comment_field_configure(
        entity_type: str,
        bundle: str,
        field_name: str = "comment",
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Configure comment field settings."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            if settings is None:
                settings = {
                    "comment_type": "comment",
                    "comment_mode": "threaded",
                    "comment_per_page": "50",
                    "comment_anonymous": False,
                    "comment_form_location": "below",
                    "comment_preview": "1",
                }
            
            import json
            settings_json = json.dumps(settings)
            cmd = ["config:set", f"field.field.{entity_type}.{bundle}.{field_name}", settings_json]
            result = await drush.run(*cmd)
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}
