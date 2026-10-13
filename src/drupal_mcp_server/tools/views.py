"""Views management tools for Drupal."""

import json
from typing import Any

from fastmcp import FastMCP


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    jsonapi = deps.get("jsonapi_client")
    graphql = deps.get("graphql_client")

    def _ensure_dict(result: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
        """Ensure result is a dict, not a list."""
        if result is None:
            return {"error": "No response"}
        if isinstance(result, list):
            return {"error": f"Unexpected list response: {result}"}
        return result

    @mcp.tool()
    async def views_list(
        filters: dict[str, Any] | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List all views on a Drupal site."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if filters:
                for key, value in filters.items():
                    params[f"filter[{key}]"] = str(value)
            
            result = await jsonapi.get_resource("views_view", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def views_get(view_id: str, include: str = "") -> dict[str, Any]:
        """Get a single view configuration by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("views_view", view_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def views_create(
        view_id: str,
        label: str,
        description: str = "",
        base_table: str = "node",
        base_field: str = "nid",
        display: list[dict[str, Any]] | None = None,
        query: dict[str, Any] | None = None,
        filter: list[dict[str, Any]] | None = None,
        sort: list[dict[str, Any]] | None = None,
        fields: list[dict[str, Any]] | None = None,
        header: list[dict[str, Any]] | None = None,
        footer: list[dict[str, Any]] | None = None,
        empty: list[dict[str, Any]] | None = None,
        relationships: list[dict[str, Any]] | None = None,
        arguments: list[dict[str, Any]] | None = None,
        contextual_filters: list[dict[str, Any]] | None = None,
        page: dict[str, Any] | None = None,
        pager: dict[str, Any] | None = None,
        style: dict[str, Any] | None = None,
        row: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new view."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            view_data: dict[str, Any] = {
                "type": "views_view",
                "id": view_id,
                "label": label,
                "description": description,
                "base_table": base_table,
                "base_field": base_field,
            }
            
            if display:
                view_data["display"] = display
            if query:
                view_data["query"] = query
            if filter:
                view_data["filter"] = filter
            if sort:
                view_data["sort"] = sort
            if fields:
                view_data["field"] = fields
            if header:
                view_data["header"] = header
            if footer:
                view_data["footer"] = footer
            if empty:
                view_data["empty"] = empty
            if relationships:
                view_data["relationship"] = relationships
            if arguments:
                view_data["argument"] = arguments
            if contextual_filters:
                view_data["contextual_filter"] = contextual_filters
            if page:
                view_data["page"] = page
            if pager:
                view_data["pager"] = pager
            if style:
                view_data["style"] = style
            if row:
                view_data["row"] = row
            
            result = await jsonapi.create_resource("views_view", view_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def views_update(
        view_id: str,
        label: str | None = None,
        description: str | None = None,
        display: list[dict[str, Any]] | None = None,
        query: dict[str, Any] | None = None,
        filter: list[dict[str, Any]] | None = None,
        sort: list[dict[str, Any]] | None = None,
        fields: list[dict[str, Any]] | None = None,
        header: list[dict[str, Any]] | None = None,
        footer: list[dict[str, Any]] | None = None,
        empty: list[dict[str, Any]] | None = None,
        relationships: list[dict[str, Any]] | None = None,
        arguments: list[dict[str, Any]] | None = None,
        contextual_filters: list[dict[str, Any]] | None = None,
        page: dict[str, Any] | None = None,
        pager: dict[str, Any] | None = None,
        style: dict[str, Any] | None = None,
        row: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update an existing view."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            # Get current view to preserve existing config
            current = await jsonapi.get_by_id("views_view", view_id)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data: dict[str, Any] = {"id": view_id, "type": "views_view"}
            if label is not None:
                update_data["label"] = label
            if description is not None:
                update_data["description"] = description
            if display is not None:
                update_data["display"] = display
            if query is not None:
                update_data["query"] = query
            if filter is not None:
                update_data["filter"] = filter
            if sort is not None:
                update_data["sort"] = sort
            if fields is not None:
                update_data["field"] = fields
            if header is not None:
                update_data["header"] = header
            if footer is not None:
                update_data["footer"] = footer
            if empty is not None:
                update_data["empty"] = empty
            if relationships is not None:
                update_data["relationship"] = relationships
            if arguments is not None:
                update_data["argument"] = arguments
            if contextual_filters is not None:
                update_data["contextual_filter"] = contextual_filters
            if page is not None:
                update_data["page"] = page
            if pager is not None:
                update_data["pager"] = pager
            if style is not None:
                update_data["style"] = style
            if row is not None:
                update_data["row"] = row
            
            result = await jsonapi.update_resource("views_view", view_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def views_delete(view_id: str) -> dict[str, Any]:
        """Delete a view."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.delete_resource("views_view", view_id)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def views_execute(
        view_id: str,
        display_id: str = "default",
        args: list[str] | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Execute a view and return results."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            # Execute view via GraphQL if available, otherwise use REST endpoint
            if graphql:
                query = f"""
                query {{
                    view(view_id: "{view_id}", display_id: "{display_id}") {{
                        result {{
                            rows
                        }}
                    }}
                }}
                """
                # Note: Actual GraphQL query would need proper args/filters
                result = await graphql.execute(query)
                return _ensure_dict(result)
            
            # Fallback: Try JSON:API endpoint for view results
            params = {"page[limit]": str(limit), "page[offset]": str(offset)}
            if args:
                params["args"] = ",".join(args)
            if filters:
                for key, value in filters.items():
                    params[f"filter[{key}]"] = str(value)
            
            # Views results often come from a custom endpoint
            result = await jsonapi.get_resource(f"views/{view_id}/{display_id}", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def views_export(
        view_id: str,
        format: str = "yaml",
    ) -> dict[str, Any]:
        """Export a view as configuration YAML or JSON."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            # Get full view configuration
            result = await jsonapi.get_by_id("views_view", view_id)
            result = _ensure_dict(result)
            
            if result.get("error"):
                return result
            
            view_data = result.get("data", {})
            
            if format == "yaml":
                import yaml
                exported = yaml.dump(view_data, default_flow_style=False, sort_keys=False)
            else:
                exported = json.dumps(view_data, indent=2)
            
            return {
                "view_id": view_id,
                "format": format,
                "config": exported,
            }
        except Exception as e:
            return {"error": str(e)}
