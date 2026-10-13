"""Taxonomy management tools for Drupal."""

from typing import Any

from fastmcp import FastMCP

from ._utils import ensure_dict as _ensure_dict, validate_pagination


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    jsonapi = deps.get("jsonapi_client")

    @mcp.tool()
    async def create_vocabulary(
        vid: str,
        name: str,
        description: str = "",
        langcode: str = "en",
    ) -> dict[str, Any]:
        """Create a taxonomy vocabulary."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            vocab_data = {
                "type": "taxonomy_vocabulary--taxonomy_vocabulary",
                "vid": vid,
                "name": name,
                "description": description,
                "langcode": langcode,
            }
            result = await jsonapi.create_resource("taxonomy_vocabulary", vocab_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def get_vocabulary(vid: str) -> dict[str, Any]:
        """Get a taxonomy vocabulary by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.get_by_id("taxonomy_vocabulary", vid)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def update_vocabulary(vid: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Update a taxonomy vocabulary."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.update_resource("taxonomy_vocabulary", vid, fields)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def delete_vocabulary(vid: str) -> dict[str, Any]:
        """Delete a taxonomy vocabulary."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.delete_resource("taxonomy_vocabulary", vid)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def list_vocabularies() -> dict[str, Any]:
        """List all taxonomy vocabularies."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.get_resource("taxonomy_vocabulary")
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def create_term(
        vid: str,
        name: str,
        description: str = "",
        parent: list[dict[str, str]] | None = None,
        weight: int = 0,
        langcode: str = "en",
    ) -> dict[str, Any]:
        """Create a taxonomy term in a vocabulary."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            term_data = {
                "type": f"taxonomy_term--{vid}",
                "name": name,
                "description": description,
                "langcode": langcode,
                "weight": weight,
            }
            if parent:
                term_data["parent"] = parent
            
            result = await jsonapi.create_resource(f"taxonomy_term--{vid}", term_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def get_term(vid: str, tid: str) -> dict[str, Any]:
        """Get a taxonomy term by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.get_by_id(f"taxonomy_term--{vid}", tid)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def update_term(vid: str, tid: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Update a taxonomy term."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.update_resource(f"taxonomy_term--{vid}", tid, fields)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def delete_term(vid: str, tid: str) -> dict[str, Any]:
        """Delete a taxonomy term."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.delete_resource(f"taxonomy_term--{vid}", tid)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def list_terms(
        vid: str,
        filters: dict[str, Any] | None = None,
        sorts: list[str] | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List terms in a vocabulary with filters and pagination."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        pag_err = validate_pagination(page_limit, page_offset)
        if pag_err:
            return pag_err
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if filters:
                for key, value in filters.items():
                    params[f"filter[{key}]"] = str(value)
            
            if sorts:
                params["sort"] = ",".join(sorts)
            
            result = await jsonapi.get_resource(f"taxonomy_term--{vid}", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}
