"""Views management tools for Drupal.

The entity type is ``view``, not ``views_view``. Drupal's config files are
called ``views.view.*.yml`` and the old pre-Drupal-8 entity was `views_view`,
so the longer name is the one that looks right -- and it 404s. JSON:API
exposes the resource as ``view--view`` (the bundle of a config entity is the
entity type itself), which is why every payload below carries that string
while the calls take ``"view"``.

Reading and writing go through JSON:API; executing a view does not, because
there is no JSON:API resource for view *results* -- it runs the view through
the Views API instead.
"""

import json
from typing import Any

from fastmcp import FastMCP

from ._utils import ensure_dict as _ensure_dict


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    jsonapi = deps.get("jsonapi_client")
    drush = deps.get("drush_client")

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
            
            result = await jsonapi.get_resource("view", params)
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
            result = await jsonapi.get_by_id("view", view_id, params=params if params else None)
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
                "type": "view--view",
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
            
            result = await jsonapi.create_resource("view", view_data)
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
            current = await jsonapi.get_by_id("view", view_id)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data: dict[str, Any] = {"id": view_id, "type": "view--view"}
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
            
            result = await jsonapi.update_resource("view", view_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def views_delete(view_id: str) -> dict[str, Any]:
        """Delete a view."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.delete_resource("view", view_id)
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
        """Execute a view and return its rows.

        Runs the view through the Views API rather than guessing at a GraphQL
        schema. The graphql module ships no `view(view_id:...)` root field, so
        the query this used to send could never resolve, and the fallback asked
        JSON:API for `views/{id}/{display}`, which is not a resource either.
        Neither path was reachable, so the tool failed wherever Views was
        installed and healthy.

        `args` are the view's contextual filters, in order. `filters` are set
        on the view's exposed input, which is what a visitor filling in the
        view's own filter form sets. A display that does not exist is reported
        along with the displays the view does have: `ViewExecutable::setDisplay`
        would otherwise fail later, with a message naming neither the view nor
        the display the caller asked for.
        """
        if not drush:
            return {"error": "Drush not available"}
        try:
            import json as _json

            args_json = _json.dumps(args or [])
            filters_json = _json.dumps(filters or {})
            # No shell is involved: the code reaches drush as one argv token,
            # so PHP quotes are literal and nothing needs escaping.
            code = (
                "$id = " + _json.dumps(view_id) + ";"
                "$display = " + _json.dumps(display_id) + ";"
                "$args = json_decode(" + _json.dumps(args_json) + ", TRUE);"
                "$filters = json_decode(" + _json.dumps(filters_json) + ", TRUE);"
                # There is no `views.views` service: the executable is built
                # from the view's config entity by `views.executable`.
                "$ve = \\Drupal::entityTypeManager()->getStorage('view')->load($id);"
                "$displays = $ve ? $ve->get('display') : [];"
                "if (!$ve) {"
                "  print json_encode(['error' => 'No view with id ' . $id]);"
                "} elseif (!isset($displays[$display])) {"
                "  print json_encode(['error' => 'View ' . $id . ' has no display '"
                "    . $display, 'available' => array_keys($displays)]);"
                "} else {"
                "  $view = \\Drupal::service('views.executable')->get($ve);"
                "  $view->setDisplay($display);"
                "  if ($args) { $view->setArguments($args); }"
                "  if ($filters) { $view->setExposedInput($filters); }"
                "  $view->execute();"
                "  $rows = [];"
                "  foreach ($view->result as $row) {"
                # ResultRow exposes the entity as a magic property, so
                # isset($row->entity) is false even when it is there; _entity
                # is the real property.
                "    $e = $row->_entity ?? NULL;"
                "    $rows[] = ['entity_type' => $e ? $e->getEntityTypeId() : NULL,"
                "               'id' => $e ? (string) $e->id() : NULL];"
                "  }"
                "  print json_encode(['view_id' => $id, 'display_id' => $display,"
                "    'total' => count($rows), 'rows' => $rows]);"
                "}"
            )
            result = await drush.run("php:eval", [code])
            payload = _ensure_dict(result)
            if payload.get("error"):
                return payload
            data = payload.get("data")
            if isinstance(data, dict) and data.get("error"):
                out = {"error": data["error"], "view_id": view_id}
                # A wrong display comes back with the ones that exist; keeping
                # them is the difference between one round trip and a guess.
                if data.get("available"):
                    out["available"] = data["available"]
                return out
            data = data if isinstance(data, dict) else {}
            rows = data.get("rows") or []
            # Truncate in PHP or here? Here: the view may legitimately produce
            # more rows than the caller asked for, and slicing the reported set
            # keeps the answer honest about what came back.
            window = rows[int(offset):int(offset) + int(limit)] if rows else []
            return {**data, "rows": window, "returned": len(window)}
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
            result = await jsonapi.get_by_id("view", view_id)
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
