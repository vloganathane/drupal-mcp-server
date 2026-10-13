"""Contact Forms tools for Drupal."""

import os
import yaml
import json
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
    async def contact_form_list(
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List all contact forms."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            result = await jsonapi.get_resource("contact_form", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def contact_form_get(
        form_id: str,
        include: str = "",
    ) -> dict[str, Any]:
        """Get a single contact form by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("contact_form", form_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def contact_form_create(
        id: str,
        label: str,
        recipients: list[str],
        reply_to: str | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        """Create a new contact form."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            form_data = {
                "type": "contact_form",
                "id": id,
                "label": label,
                "recipients": recipients,
            }
            if reply_to:
                form_data["reply_to"] = reply_to
            if message:
                form_data["message"] = message
            
            result = await jsonapi.create_resource("contact_form", form_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def contact_form_update(
        form_id: str,
        label: str | None = None,
        recipients: list[str] | None = None,
        reply_to: str | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        """Update a contact form."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            current = await jsonapi.get_by_id("contact_form", form_id)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data: dict[str, Any] = {"id": form_id, "type": "contact_form"}
            if label is not None:
                update_data["label"] = label
            if recipients is not None:
                update_data["recipients"] = recipients
            if reply_to is not None:
                update_data["reply_to"] = reply_to
            if message is not None:
                update_data["message"] = message
            
            result = await jsonapi.update_resource("contact_form", form_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def contact_form_delete(
        form_id: str,
    ) -> dict[str, Any]:
        """Delete a contact form."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.delete_resource("contact_form", form_id)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def contact_message_list(
        form_id: str | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List contact form submissions."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if form_id:
                params["filter[contact_form]"] = form_id
            
            result = await jsonapi.get_resource("contact_message", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def contact_message_get(
        message_id: str,
        include: str = "",
    ) -> dict[str, Any]:
        """Get a single contact message by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("contact_message", message_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def contact_message_delete(
        message_id: str,
    ) -> dict[str, Any]:
        """Delete a contact message."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.delete_resource("contact_message", message_id)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def contact_spam_check(
        message_id: str,
    ) -> dict[str, Any]:
        """Check if a contact message is spam."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["exec", [
                f"\\$message = \\Drupal::entityTypeManager()->getStorage('contact_message')->load('{message_id}'); "
                f"\\$spam = \\Drupal::service('contact.spam')->check(\\$message); "
                f"print_r(json_encode(['spam' => \\$spam]));"
            ]]
            result = await drush.run(*cmd)
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}
