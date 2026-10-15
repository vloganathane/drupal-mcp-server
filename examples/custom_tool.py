#!/usr/bin/env python3
"""Custom tool example for Drupal MCP Server.

Demonstrates how to create a custom tool module that integrates with
the Drupal MCP Server architecture.

This example shows:
1. How to structure a tool module
2. How to use shared utilities
3. How to handle errors consistently
4. How to validate input

To use this example:
1. Copy to src/drupal_mcp_server/tools/my_custom.py
2. Import and register in server.py
3. Restart the server
"""

from typing import Any

from fastmcp import FastMCP

from ._utils import ensure_dict, validate_identifier, validate_pagination


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    """Register custom tools with the MCP server.

    Args:
        mcp: FastMCP server instance
        **deps: Dependencies injected by the server (jsonapi_client, drush_client, etc.)
    """
    jsonapi = deps.get("jsonapi_client")

    @mcp.tool()
    async def get_content_summary(bundle: str, page_limit: int = 10) -> dict[str, Any]:
        """Get a summary of content for a given bundle.

        Args:
            bundle: Content type bundle (e.g., 'article', 'page')
            page_limit: Maximum number of items to return (1-500)

        Returns:
            Summary containing count, titles, and IDs of content items

        Raises:
            ValueError: If bundle name is invalid
            ClientError: If the JSON:API request fails

        Example:
            >>> result = await get_content_summary("article", 5)
            >>> print(result["total"])
        """
        # Validate inputs
        bundle_error = validate_identifier(bundle, "bundle")
        if bundle_error:
            return {"error": bundle_error}

        pagination_error = validate_pagination(page_limit, 0)
        if pagination_error:
            return pagination_error

        if not jsonapi:
            return {"error": "JSON:API not available"}

        try:
            result = await jsonapi.get_resource(
                f"node--{bundle}",
                {"page[limit]": str(page_limit)}
            )
            result = ensure_dict(result)

            if result.get("error"):
                return result

            data = result.get("data", [])
            return {
                "bundle": bundle,
                "total": len(data),
                "items": [
                    {
                        "id": item.get("id"),
                        "title": item.get("attributes", {}).get("title", "Untitled")
                    }
                    for item in data
                ]
            }
        except Exception as e:
            return {"error": f"Failed to fetch content: {str(e)}"}

    @mcp.tool()
    async def search_content(query: str, bundle: str | None = None) -> dict[str, Any]:
        """Search content by title.

        Args:
            query: Search query string
            bundle: Optional bundle filter

        Returns:
            List of matching content items

        Raises:
            ValueError: If query is empty or too long
        """
        if not query or not query.strip():
            return {"error": "Query cannot be empty"}
        if len(query) > 255:
            return {"error": "Query exceeds maximum length of 255 characters"}

        if not jsonapi:
            return {"error": "JSON:API not available"}

        try:
            params = {"filter[title]": query}
            resource = f"node--{bundle}" if bundle else "node"
            result = await jsonapi.get_resource(resource, params)
            result = ensure_dict(result)

            if result.get("error"):
                return result

            return {
                "query": query,
                "bundle": bundle,
                "results": result.get("data", []),
                "count": len(result.get("data", []))
            }
        except Exception as e:
            return {"error": f"Search failed: {str(e)}"}
