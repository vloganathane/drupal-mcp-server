"""User management tools for Drupal."""

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
    async def create_user(
        mail: str,
        name: str,
        pass_: str | None = None,
        status: bool = True,
        roles: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a user account."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            user_data = {
                "type": "user--user",
                "name": name,
                "mail": mail,
                "status": status,
            }
            if pass_:
                user_data["pass"] = pass_
            
            result = await jsonapi.create_resource("user--user", user_data)
            result = _ensure_dict(result)
            
            # Assign roles if provided
            if roles and not result.get("error"):
                uid = result.get("data", {}).get("id")
                if uid and drush:
                    for role in roles:
                        await drush.run("user:role:add", [role, uid])
            
            return result
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def get_user(uid: str, include: str = "") -> dict[str, Any]:
        """Get a user by ID with optional relationship includes."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("user--user", uid, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def get_user_by_email(mail: str) -> dict[str, Any]:
        """Get a user by email address."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.get_resource("user--user", {"filter[mail]": mail})
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def update_user(uid: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Update a user account."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            current = await jsonapi.get_by_id("user--user", uid)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data = {**fields, "id": uid, "type": "user--user"}
            result = await jsonapi.update_resource("user--user", uid, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def delete_user(uid: str) -> dict[str, Any]:
        """Delete a user account."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.delete_resource("user--user", uid)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def list_users(
        filters: dict[str, Any] | None = None,
        sorts: list[str] | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List users with filters and pagination."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if filters:
                for key, value in filters.items():
                    params[f"filter[{key}]"] = str(value)
            
            if sorts:
                params["sort"] = ",".join(sorts)
            
            result = await jsonapi.get_resource("user--user", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def assign_role(uid: str, role: str) -> dict[str, Any]:
        """Assign a role to a user."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("user:role:add", [role, uid])
            return {"returncode": result.get("returncode"), "output": result.get("data", {})}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def remove_role(uid: str, role: str) -> dict[str, Any]:
        """Remove a role from a user."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("user:role:remove", [role, uid])
            return {"returncode": result.get("returncode"), "output": result.get("data", {})}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def list_roles() -> dict[str, Any]:
        """List all available roles."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("role:list", ["--format=json"])
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def get_user_roles(uid: str) -> dict[str, Any]:
        """Get roles assigned to a user."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("user:role:list", [uid, "--format=json"])
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def block_user(uid: str) -> dict[str, Any]:
        """Block a user account."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.update_resource("user--user", uid, {"id": uid, "type": "user--user", "status": False})
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def unblock_user(uid: str) -> dict[str, Any]:
        """Unblock a user account."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.update_resource("user--user", uid, {"id": uid, "type": "user--user", "status": True})
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}
