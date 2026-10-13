"""Drupal.org API integration tools."""

from typing import Any

import httpx
from fastmcp import FastMCP

from ._utils import ensure_dict as _ensure_dict


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    DRUPAL_ORG_API_BASE = "https://www.drupal.org/api-d7"

    async def _drupal_org_request(endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make a request to Drupal.org API."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                url = f"{DRUPAL_ORG_API_BASE}/{endpoint.lstrip('/')}"
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                if isinstance(data, list):
                    return {"data": data}
                return data  # type: ignore[no-any-return]
        except httpx.HTTPStatusError as e:
            return {"error": f"HTTP {e.response.status_code}: {e.response.text}"}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def module_search(
        query: str,
        type: str = "module",
        status: str = "published",
        sort: str = "relevance",
        page: int = 0,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """Search modules on Drupal.org."""
        params = {
            "q": query,
            "type": type,
            "status": status,
            "sort": sort,
            "page": page,
            "page_size": page_size,
        }
        result = await _drupal_org_request("search", params)
        return _ensure_dict(result)

    @mcp.tool()
    async def module_get(project_id: str) -> dict[str, Any]:
        """Get module details by project ID or machine name."""
        result = await _drupal_org_request(f"project/{project_id}")
        return _ensure_dict(result)

    @mcp.tool()
    async def module_versions(project_id: str) -> dict[str, Any]:
        """Get all available versions for a module."""
        result = await _drupal_org_request(f"project/{project_id}/releases")
        return _ensure_dict(result)

    @mcp.tool()
    async def module_dependencies(project_id: str, version: str | None = None) -> dict[str, Any]:
        """Get module dependencies."""
        endpoint = f"project/{project_id}/dependencies"
        if version:
            endpoint += f"?version={version}"
        result = await _drupal_org_request(endpoint)
        return _ensure_dict(result)

    @mcp.tool()
    async def theme_search(
        query: str,
        status: str = "published",
        sort: str = "relevance",
        page: int = 0,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """Search themes on Drupal.org."""
        params = {
            "q": query,
            "type": "theme",
            "status": status,
            "sort": sort,
            "page": page,
            "page_size": page_size,
        }
        result = await _drupal_org_request("search", params)
        return _ensure_dict(result)

    @mcp.tool()
    async def theme_get(project_id: str) -> dict[str, Any]:
        """Get theme details by project ID or machine name."""
        result = await _drupal_org_request(f"project/{project_id}")
        return _ensure_dict(result)

    @mcp.tool()
    async def release_history(project_id: str) -> dict[str, Any]:
        """Get release history for a project."""
        result = await _drupal_org_request(f"project/{project_id}/releases")
        return _ensure_dict(result)

    @mcp.tool()
    async def project_usage(project_id: str, period: str = "month") -> dict[str, Any]:
        """Get project usage statistics."""
        params = {"period": period}
        result = await _drupal_org_request(f"project/{project_id}/usage", params)
        return _ensure_dict(result)

    @mcp.tool()
    async def module_compatibility(project_id: str, core_version: str = "10") -> dict[str, Any]:
        """Check module compatibility with a Drupal core version."""
        result = await _drupal_org_request(f"project/{project_id}/compatibility/{core_version}")
        return _ensure_dict(result)
