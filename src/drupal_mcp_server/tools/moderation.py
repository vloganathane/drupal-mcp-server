"""Content moderation workflow tools for Drupal."""

from typing import Any

from fastmcp import FastMCP

from ._utils import ensure_dict as _ensure_dict, validate_pagination


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    jsonapi = deps.get("jsonapi_client")
    drush = deps.get("drush_client")

    @mcp.tool()
    async def moderation_state_list(
        filters: dict[str, Any] | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List all moderation states."""
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
            
            result = await jsonapi.get_resource("moderation_state", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def moderation_state_get(state_id: str, include: str = "") -> dict[str, Any]:
        """Get a single moderation state by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("moderation_state", state_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def moderation_state_create(
        workflow_id: str,
        state_id: str,
        label: str,
        weight: int = 0,
        is_default: bool = False,
    ) -> dict[str, Any]:
        """Create a new moderation state."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            state_data = {
                "type": "moderation_state",
                "id": state_id,
                "workflow": workflow_id,
                "label": label,
                "weight": weight,
                "is_default": is_default,
            }
            
            result = await jsonapi.create_resource("moderation_state", state_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def moderation_state_update(
        state_id: str,
        label: str | None = None,
        weight: int | None = None,
        is_default: bool | None = None,
    ) -> dict[str, Any]:
        """Update a moderation state."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            current = await jsonapi.get_by_id("moderation_state", state_id)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data: dict[str, Any] = {"id": state_id, "type": "moderation_state"}
            if label is not None:
                update_data["label"] = label
            if weight is not None:
                update_data["weight"] = weight
            if is_default is not None:
                update_data["is_default"] = is_default
            
            result = await jsonapi.update_resource("moderation_state", state_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def moderation_state_delete(state_id: str) -> dict[str, Any]:
        """Delete a moderation state."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.delete_resource("moderation_state", state_id)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def moderation_transition_list(
        workflow_id: str | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List moderation transitions."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        pag_err = validate_pagination(page_limit, page_offset)
        if pag_err:
            return pag_err
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if workflow_id:
                params["filter[workflow]"] = workflow_id
            
            result = await jsonapi.get_resource("workflow_transition", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def moderation_transition_get(transition_id: str, include: str = "") -> dict[str, Any]:
        """Get a single moderation transition by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("workflow_transition", transition_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def moderation_transition_create(
        workflow_id: str,
        transition_id: str,
        label: str,
        from_states: list[str],
        to_state: str,
        weight: int = 0,
    ) -> dict[str, Any]:
        """Create a new moderation transition."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            transition_data = {
                "type": "workflow_transition",
                "id": transition_id,
                "workflow": workflow_id,
                "label": label,
                "from": from_states,
                "to": to_state,
                "weight": weight,
            }
            
            result = await jsonapi.create_resource("workflow_transition", transition_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def moderation_transition_execute(
        entity_type: str,
        entity_id: str,
        transition_id: str,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        """Execute a moderation transition on an entity."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            # Get current entity to find its current state
            entity_resource = f"{entity_type}--{entity_type}"
            entity = await jsonapi.get_by_id(entity_resource, entity_id)
            entity = _ensure_dict(entity)
            if entity.get("error"):
                return entity
            
            # Get the transition to verify it's valid
            transition = await jsonapi.get_by_id("workflow_transition", transition_id)
            transition = _ensure_dict(transition)
            if transition.get("error"):
                return transition
            
            # Apply the transition
            current_state = entity.get("data", {}).get("attributes", {}).get("moderation_state", "")
            transition_data = transition.get("data", {}).get("attributes", {})
            from_states = transition_data.get("from", [])
            to_state = transition_data.get("to", "")
            
            if current_state not in from_states:
                return {"error": f"Entity is in state '{current_state}', but transition requires one of: {from_states}"}
            
            # Update entity with new moderation state
            update_data = {
                "id": entity_id,
                "type": f"{entity_type}--{entity_type}",
                "moderation_state": to_state,
            }
            if user_id:
                update_data["uid"] = user_id
            
            result = await jsonapi.update_resource(entity_resource, entity_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def content_moderation_dashboard(
        filters: dict[str, Any] | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """Get content pending moderation - dashboard view."""
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
            
            # Find nodes with non-published moderation states
            params["filter[moderation_state][!="] = "published"
            
            result = await jsonapi.get_resource("node", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def workflow_list(
        filters: dict[str, Any] | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List all workflows."""
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
            
            result = await jsonapi.get_resource("workflow", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def workflow_get(workflow_id: str, include: str = "") -> dict[str, Any]:
        """Get a single workflow by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("workflow", workflow_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}
