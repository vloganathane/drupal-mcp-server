"""Menus management tools for Drupal."""

from typing import Any

from fastmcp import FastMCP

from ._utils import ensure_dict as _ensure_dict


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    jsonapi = deps.get("jsonapi_client")

    @mcp.tool()
    async def menu_list(
        filters: dict[str, Any] | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List all menus on a Drupal site."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if filters:
                for key, value in filters.items():
                    params[f"filter[{key}]"] = str(value)
            
            result = await jsonapi.get_resource("menu", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def menu_get(menu_id: str, include: str = "") -> dict[str, Any]:
        """Get a single menu configuration by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("menu", menu_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def menu_create(
        menu_id: str,
        label: str,
        description: str = "",
        langcode: str = "en",
    ) -> dict[str, Any]:
        """Create a new menu."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            menu_data = {
                "type": "menu",
                "id": menu_id,
                "label": label,
                "description": description,
                "langcode": langcode,
            }
            
            result = await jsonapi.create_resource("menu", menu_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def menu_update(
        menu_id: str,
        label: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing menu."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            # Get current menu to preserve existing config
            current = await jsonapi.get_by_id("menu", menu_id)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data: dict[str, Any] = {"id": menu_id, "type": "menu"}
            if label is not None:
                update_data["label"] = label
            if description is not None:
                update_data["description"] = description
            
            result = await jsonapi.update_resource("menu", menu_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def menu_delete(menu_id: str) -> dict[str, Any]:
        """Delete a menu."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.delete_resource("menu", menu_id)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def menu_link_list(
        menu_id: str | None = None,
        filters: dict[str, Any] | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List menu links, optionally filtered by menu."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if menu_id:
                # `menu` is not a field on menu_link_content, so filtering on
                # it made Drupal answer 400 "Invalid nested filtering ... the
                # field `menu`, given in the path `menu`, does not exist" on
                # every call, on every site. The field is `menu_name`.
                params["filter[menu_name]"] = menu_id
            
            if filters:
                for key, value in filters.items():
                    params[f"filter[{key}]"] = str(value)
            
            result = await jsonapi.get_resource("menu_link_content", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def menu_link_get(link_id: str, include: str = "") -> dict[str, Any]:
        """Get a single menu link by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("menu_link_content", link_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def menu_link_create(
        menu_id: str,
        title: str,
        link: dict[str, Any],
        description: str = "",
        weight: int = 0,
        expanded: bool = False,
        parent: str | None = None,
    ) -> dict[str, Any]:
        """Create a new menu link."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            link_data = {
                "type": "menu_link_content",
                "title": title,
                "menu": menu_id,
                "link": link,
                "description": description,
                "weight": weight,
                "expanded": expanded,
            }
            if parent:
                link_data["parent"] = parent
            
            result = await jsonapi.create_resource("menu_link_content", link_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def menu_link_update(
        link_id: str,
        title: str | None = None,
        link: dict[str, Any] | None = None,
        description: str | None = None,
        weight: int | None = None,
        expanded: bool | None = None,
        parent: str | None = None,
    ) -> dict[str, Any]:
        """Update a menu link."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            # Get current link to preserve existing config
            current = await jsonapi.get_by_id("menu_link_content", link_id)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data: dict[str, Any] = {"id": link_id, "type": "menu_link_content"}
            if title is not None:
                update_data["title"] = title
            if link is not None:
                update_data["link"] = link
            if description is not None:
                update_data["description"] = description
            if weight is not None:
                update_data["weight"] = weight
            if expanded is not None:
                update_data["expanded"] = expanded
            if parent is not None:
                update_data["parent"] = parent
            
            result = await jsonapi.update_resource("menu_link_content", link_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def menu_link_delete(link_id: str) -> dict[str, Any]:
        """Delete a menu link."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.delete_resource("menu_link_content", link_id)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}
