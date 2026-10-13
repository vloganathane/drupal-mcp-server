"""Redirects management tools for Drupal."""

from typing import Any

from fastmcp import FastMCP


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    jsonapi = deps.get("jsonapi_client")
    drush = deps.get("drush_client")

    def _ensure_dict(result: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
        """Ensure result is a dict, not a list."""
        if result is None:
            return {"error": "No response"}
        if isinstance(result, list):
            return {"error": f"Unexpected list response: {result}"}
        return result

    @mcp.tool()
    async def redirect_list(
        filters: dict[str, Any] | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List all redirects on a Drupal site."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if filters:
                for key, value in filters.items():
                    params[f"filter[{key}]"] = str(value)
            
            result = await jsonapi.get_resource("redirect", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def redirect_get(redirect_id: str, include: str = "") -> dict[str, Any]:
        """Get a single redirect configuration by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("redirect", redirect_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def redirect_create(
        redirect_source: str,
        redirect_redirect: str,
        redirect_source_options: dict[str, Any] | None = None,
        redirect_redirect_options: dict[str, Any] | None = None,
        status_code: int = 301,
        language: str | None = None,
    ) -> dict[str, Any]:
        """Create a new redirect."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            redirect_data = {
                "type": "redirect",
                "redirect_source": {
                    "path": redirect_source,
                    "options": redirect_source_options or {},
                },
                "redirect_redirect": {
                    "path": redirect_redirect,
                    "options": redirect_redirect_options or {},
                },
                "status_code": status_code,
            }
            if language:
                redirect_data["language"] = language
            
            result = await jsonapi.create_resource("redirect", redirect_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def redirect_update(
        redirect_id: str,
        redirect_source: str | None = None,
        redirect_redirect: str | None = None,
        redirect_source_options: dict[str, Any] | None = None,
        redirect_redirect_options: dict[str, Any] | None = None,
        status_code: int | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing redirect."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            # Get current redirect to preserve existing config
            current = await jsonapi.get_by_id("redirect", redirect_id)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data: dict[str, Any] = {"id": redirect_id, "type": "redirect"}
            if redirect_source is not None:
                update_data["redirect_source"] = {
                    "path": redirect_source,
                    "options": redirect_source_options or {},
                }
            if redirect_redirect is not None:
                update_data["redirect_redirect"] = {
                    "path": redirect_redirect,
                    "options": redirect_redirect_options or {},
                }
            if status_code is not None:
                update_data["status_code"] = status_code
            if language is not None:
                update_data["language"] = language
            
            result = await jsonapi.update_resource("redirect", redirect_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def redirect_delete(redirect_id: str) -> dict[str, Any]:
        """Delete a redirect."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.delete_resource("redirect", redirect_id)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def redirect_bulk_create(
        redirects: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Create multiple redirects in bulk."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            created = []
            errors = []
            
            for idx, redirect in enumerate(redirects):
                try:
                    redirect_data = {
                        "type": "redirect",
                        "redirect_source": {
                            "path": redirect.get("source", ""),
                            "options": redirect.get("source_options", {}),
                        },
                        "redirect_redirect": {
                            "path": redirect.get("target", ""),
                            "options": redirect.get("target_options", {}),
                        },
                        "status_code": redirect.get("status_code", 301),
                    }
                    if redirect.get("language"):
                        redirect_data["language"] = redirect["language"]
                    
                    result = await jsonapi.create_resource("redirect", redirect_data)
                    result = _ensure_dict(result)
                    if result.get("error"):
                        errors.append({"index": idx, "error": result["error"]})
                    else:
                        created.append(result)
                except Exception as e:
                    errors.append({"index": idx, "error": str(e)})
            
            return {"created": len(created), "errors": errors, "redirects": created}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def redirect_bulk_delete(redirect_ids: list[str]) -> dict[str, Any]:
        """Delete multiple redirects in bulk."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            deleted = []
            errors = []
            
            for idx, redirect_id in enumerate(redirect_ids):
                try:
                    result = await jsonapi.delete_resource("redirect", redirect_id)
                    result = _ensure_dict(result)
                    if result.get("error"):
                        errors.append({"index": idx, "redirect_id": redirect_id, "error": result["error"]})
                    else:
                        deleted.append(redirect_id)
                except Exception as e:
                    errors.append({"index": idx, "redirect_id": redirect_id, "error": str(e)})
            
            return {"deleted": len(deleted), "errors": errors}
        except Exception as e:
            return {"error": str(e)}
