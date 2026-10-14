"""Webform tools for Drupal."""

from typing import Any

from fastmcp import FastMCP

from ._utils import absent_entity as _absent_entity
from ._utils import ensure_dict as _ensure_dict


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")
    jsonapi = deps.get("jsonapi_client")

    @mcp.tool()
    async def webform_list(
        filters: dict[str, Any] | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List all webforms."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if filters:
                for key, value in filters.items():
                    params[f"filter[{key}]"] = str(value)
            
            result = await jsonapi.get_resource("webform", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def webform_get(
        webform_id: str,
        include: str = "",
    ) -> dict[str, Any]:
        """Get a single webform by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("webform", webform_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def webform_create(
        id: str,
        label: str,
        description: str = "",
        status: bool = True,
        elements: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create a new webform."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            webform_data = {
                "type": "webform",
                "id": id,
                "label": label,
                "description": description,
                "status": status,
            }
            if elements:
                webform_data["elements"] = elements
            
            result = await jsonapi.create_resource("webform", webform_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def webform_update(
        webform_id: str,
        label: str | None = None,
        description: str | None = None,
        status: bool | None = None,
        elements: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Update a webform."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            current = await jsonapi.get_by_id("webform", webform_id)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data: dict[str, Any] = {"id": webform_id, "type": "webform"}
            if label is not None:
                update_data["label"] = label
            if description is not None:
                update_data["description"] = description
            if status is not None:
                update_data["status"] = status
            if elements is not None:
                update_data["elements"] = elements
            
            result = await jsonapi.update_resource("webform", webform_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def webform_delete(
        webform_id: str,
    ) -> dict[str, Any]:
        """Delete a webform."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.delete_resource("webform", webform_id)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def webform_submission_list(
        webform_id: str | None = None,
        filters: dict[str, Any] | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List webform submissions."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if webform_id:
                # The field is `webform_id` (not `webform`) and it is a
                # reference to the webform, so JSON:API wants the `.id`
                # specifier.
                params["filter[webform_id.id]"] = webform_id
            if filters:
                for key, value in filters.items():
                    params[f"filter[{key}]"] = str(value)
            
            result = await jsonapi.get_resource("webform_submission", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def webform_submission_get(
        submission_id: str,
        include: str = "",
    ) -> dict[str, Any]:
        """Get a single webform submission by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("webform_submission", submission_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def webform_submission_delete(
        submission_id: str,
    ) -> dict[str, Any]:
        """Delete a webform submission."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.delete_resource("webform_submission", submission_id)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def webform_element_list(
        webform_id: str,
    ) -> dict[str, Any]:
        """List elements in a webform."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            webform = await jsonapi.get_by_id("webform", webform_id)
            webform = _ensure_dict(webform)
            if webform.get("error"):
                return webform
            
            elements = webform.get("data", {}).get("attributes", {}).get("elements", {})
            return _ensure_dict({"elements": elements})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def webform_element_create(
        webform_id: str,
        element_key: str,
        element_type: str,
        label: str,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Add an element to a webform."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            webform = await jsonapi.get_by_id("webform", webform_id)
            webform = _ensure_dict(webform)
            if webform.get("error"):
                return webform
            
            elements = webform.get("data", {}).get("attributes", {}).get("elements", {})
            elements[element_key] = {
                "#type": element_type,
                "#title": label,
            }
            if properties:
                elements[element_key].update(properties)
            
            return await webform_update(webform_id, elements=elements)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def webform_handler_list(
        webform_id: str | None = None,
        page_limit: int = 50,
    ) -> dict[str, Any]:
        """List the handlers attached to a webform.

        Handlers are plugins configured on the webform, not entities, so there
        is no `webform_handler` resource for JSON:API to list. This reads them
        off the webform instead, which is where they live.
        """
        if not drush:
            return {"error": "Drush not available"}
        if not webform_id:
            return {
                "error": (
                    "webform_id is required: handlers belong to a webform, so "
                    "there is no site-wide list to return."
                )
            }
        try:
            import json as _json

            code = (
                "$wf = \\Drupal::entityTypeManager()->getStorage('webform')"
                "->load(" + _json.dumps(webform_id) + ");"
                "if (!$wf) {"
                "  print json_encode(['error' => 'No webform with id " + _json.dumps(webform_id) + "']);"
                "} else {"
                "  $out = [];"
                "  foreach ($wf->getHandlers() as $h) {"
                "    $out[] = ['id' => $h->getHandlerId(), 'label' => (string) $h->label(),"
                "              'type' => $h->getPluginId()];"
                "  }"
                "  print json_encode(['webform_id' => " + _json.dumps(webform_id) + ","
                "    'count' => count($out), 'handlers' => array_slice($out, 0, " + str(max(1, int(page_limit))) + ")]);"
                "}"
            )
            result = await drush.run("php:eval", [code])
            payload = _ensure_dict(result)
            if payload.get("error"):
                return payload
            data = payload.get("data")
            if isinstance(data, dict) and data.get("error"):
                return {"error": data["error"], "webform_id": webform_id}
            return data if isinstance(data, dict) else {}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def webform_handler_create(
        id: str,
        webform_id: str,
        handler_type: str,
        label: str,
        configuration: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a webform handler (email, remote post, etc.).

        Not implemented: a handler is a plugin held inside the webform's own
        configuration and is written through the webform form, not as an
        entity. JSON:API has no `webform_handler` resource, so the POST this
        used to send could never succeed.
        """
        return _absent_entity(
            "webform_handler",
            "Handlers are plugins stored inside the webform's configuration and "
            "are added through the webform form. Read them with "
            "webform_handler_list.",
        )

    @mcp.tool()
    async def webform_handler_update(
        handler_id: str,
        label: str | None = None,
        configuration: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update a webform handler.

        Not implemented; see `webform_handler_create`. A handler has no entity
        id of its own to address.
        """
        return _absent_entity(
            "webform_handler",
            "Handlers live inside the webform's configuration, so there is no "
            "entity to update. Read them with webform_handler_list.",
        )

    @mcp.tool()
    async def webform_handler_delete(
        handler_id: str,
    ) -> dict[str, Any]:
        """Delete a webform handler.

        Not implemented; see `webform_handler_create`.
        """
        return _absent_entity(
            "webform_handler",
            "Handlers live inside the webform's configuration, so there is no "
            "entity to delete. Read them with webform_handler_list.",
        )

    @mcp.tool()
    async def webform_token_list(
        webform_id: str | None = None,
    ) -> dict[str, Any]:
        """List available webform tokens."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["token:list"]
            if webform_id:
                cmd.append(f"webform.{webform_id}")
            result = await drush.run(*cmd)
            return _ensure_dict({"tokens": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def webform_export_submissions(
        webform_id: str,
        format: str = "csv",
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Export webform submissions."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["webform:submission:export", webform_id, f"--format={format}"]
            if filters:
                for key, value in filters.items():
                    cmd.extend([f"--{key}", str(value)])
            result = await drush.run(*cmd)
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}
