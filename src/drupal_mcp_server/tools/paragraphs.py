"""Paragraphs management tools for Drupal."""

from typing import Any

from fastmcp import FastMCP

from ._utils import ensure_dict as _ensure_dict


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    jsonapi = deps.get("jsonapi_client")

    @mcp.tool()
    async def paragraphs_type_list(
        filters: dict[str, Any] | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List all paragraph types on a Drupal site."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if filters:
                for key, value in filters.items():
                    params[f"filter[{key}]"] = str(value)
            
            result = await jsonapi.get_resource("paragraphs_type", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def paragraphs_type_get(type_id: str, include: str = "") -> dict[str, Any]:
        """Get a single paragraph type configuration by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("paragraphs_type", type_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def paragraphs_type_create(
        type_id: str,
        label: str,
        description: str = "",
        weight: int = 0,
    ) -> dict[str, Any]:
        """Create a new paragraph type."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            type_data = {
                "type": "paragraphs_type",
                "id": type_id,
                "label": label,
                "description": description,
                "weight": weight,
            }
            
            result = await jsonapi.create_resource("paragraphs_type", type_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def paragraphs_type_update(
        type_id: str,
        label: str | None = None,
        description: str | None = None,
        weight: int | None = None,
    ) -> dict[str, Any]:
        """Update an existing paragraph type."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            # Get current type to preserve existing config
            current = await jsonapi.get_by_id("paragraphs_type", type_id)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data: dict[str, Any] = {"id": type_id, "type": "paragraphs_type"}
            if label is not None:
                update_data["label"] = label
            if description is not None:
                update_data["description"] = description
            if weight is not None:
                update_data["weight"] = weight
            
            result = await jsonapi.update_resource("paragraphs_type", type_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def paragraphs_type_delete(type_id: str) -> dict[str, Any]:
        """Delete a paragraph type."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.delete_resource("paragraphs_type", type_id)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def paragraphs_item_list(
        type_id: str | None = None,
        filters: dict[str, Any] | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List paragraph items, optionally filtered by type.

        A paragraph's type is its bundle, so filtering by type means addressing
        the `paragraph--{type}` collection. `filter[paragraphs_type]` does not
        exist -- it answered 400 "the field `paragraphs_type` does not exist" on
        every call, because there is no such field; the type lives in the
        resource type itself.
        """
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if filters:
                for key, value in filters.items():
                    params[f"filter[{key}]"] = str(value)
            
            resource = f"paragraph--{type_id}" if type_id else "paragraph"
            result = await jsonapi.get_resource(resource, params)
            return _ensure_dict(result)
        except Exception as e:
            # `paragraph--{type}` addresses a bundle collection, and a bundle
            # that does not exist answers a bare 404 that names no
            # alternatives -- which reads as "paragraphs are missing" rather
            # than "that type is not configured here". Say which types there
            # are. The old `filter[paragraphs_type]` never got this far: there
            # is no such field, so it 400'd on every call.
            if type_id and "404" in str(e):
                available: list[str] = []
                try:
                    listed = await jsonapi.get_resource(
                        "paragraphs_type", {"page[limit]": "50"}
                    )
                    rows = _ensure_dict(listed).get("data") or []
                    if isinstance(rows, list):
                        for row in rows:
                            if not isinstance(row, dict):
                                continue
                            attrs = row.get("attributes") or {}
                            found = attrs.get("drupal_internal__id") or row.get("id")
                            if found:
                                available.append(str(found))
                except Exception:
                    pass
                return {
                    "error": f"This site has no paragraph type `{type_id}`.",
                    "available": available,
                }
            return {"error": str(e)}

    @mcp.tool()
    async def paragraphs_item_get(paragraph_id: str, include: str = "") -> dict[str, Any]:
        """Get a single paragraph item by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("paragraph", paragraph_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def paragraphs_item_create(
        type_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a new paragraph item of the specified type."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            paragraph_data = {
                "type": "paragraph",
                "paragraphs_type": type_id,
            }
            paragraph_data.update(fields)
            
            result = await jsonapi.create_resource("paragraph", paragraph_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def paragraphs_item_update(
        paragraph_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """Update a paragraph item."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            # Get current paragraph to preserve type
            current = await jsonapi.get_by_id("paragraph", paragraph_id)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data = {**fields, "id": paragraph_id, "type": "paragraph"}
            
            result = await jsonapi.update_resource("paragraph", paragraph_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def paragraphs_item_delete(paragraph_id: str) -> dict[str, Any]:
        """Delete a paragraph item."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.delete_resource("paragraph", paragraph_id)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}
