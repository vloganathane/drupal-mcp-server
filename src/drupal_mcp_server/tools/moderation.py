"""Content moderation workflow tools for Drupal."""

from typing import Any

from fastmcp import FastMCP

from ._utils import absent_entity as _absent_entity
from ._utils import ensure_dict as _ensure_dict
from ._utils import validate_pagination


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    jsonapi = deps.get("jsonapi_client")
    _drush = deps.get("drush_client")
    # The transition tools below read and write the `workflow` entity, since
    # transitions are configuration inside it rather than entities themselves.
    drush = _drush

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
            
            result = await jsonapi.get_resource("content_moderation_state", params)
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
            result = await jsonapi.get_by_id("content_moderation_state", state_id, params=params if params else None)
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
                "type": "content_moderation_state--content_moderation_state",
                "id": state_id,
                "workflow": workflow_id,
                "label": label,
                "weight": weight,
                "is_default": is_default,
            }
            
            result = await jsonapi.create_resource("content_moderation_state", state_data)
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
            current = await jsonapi.get_by_id("content_moderation_state", state_id)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data: dict[str, Any] = {"id": state_id, "type": "content_moderation_state--content_moderation_state"}
            if label is not None:
                update_data["label"] = label
            if weight is not None:
                update_data["weight"] = weight
            if is_default is not None:
                update_data["is_default"] = is_default
            
            result = await jsonapi.update_resource("content_moderation_state", state_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def moderation_state_delete(state_id: str) -> dict[str, Any]:
        """Delete a moderation state."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.delete_resource("content_moderation_state", state_id)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def moderation_transition_list(
        workflow_id: str | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List a workflow's moderation transitions.

        Transitions are configuration *inside* the `workflow` entity, not
        entities of their own, so there is no `workflow_transition` resource
        for JSON:API to list. This reads them off the workflow instead, which
        is where they are defined.
        """
        if not drush:
            return {"error": "Drush not available"}
        pag_err = validate_pagination(page_limit, page_offset)
        if pag_err:
            return pag_err
        try:
            import json as _json

            ids = [workflow_id] if workflow_id else None
            code = (
                "$tm = \\Drupal::entityTypeManager();"
                "$ids = " + _json.dumps(ids) + ";"
                "$workflows = $ids ? $tm->getStorage('workflow')->loadMultiple($ids)"
                "                  : $tm->getStorage('workflow')->loadMultiple();"
                "$out = [];"
                "foreach ($workflows as $wf) {"
                "  foreach ((array) $wf->get('transitions') as $tid => $t) {"
                "    $out[] = ['id' => (string) $tid, 'workflow' => $wf->id(),"
                "      'label' => (string) ($t['label'] ?? ''),"
                "      'from' => (array) ($t['from'] ?? []),"
                "      'to' => (string) ($t['to'] ?? ''),"
                "      'weight' => (int) ($t['weight'] ?? 0)];"
                "  }"
                "}"
                "print json_encode(array_values($out));"
            )
            result = await drush.run("php:eval", [code])
            payload = _ensure_dict(result)
            if payload.get("error"):
                return payload
            rows = payload.get("data") or []
            start = int(page_offset)
            window = rows[start:start + int(page_limit)]
            return {"count": len(rows), "transitions": window}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def moderation_transition_get(transition_id: str, include: str = "") -> dict[str, Any]:
        """Get a single moderation transition by ID.

        Transitions belong to a workflow rather than being entities, so this
        searches every workflow for the named transition.
        """
        if not drush:
            return {"error": "Drush not available"}
        try:
            import json as _json

            code = (
                "$tid = " + _json.dumps(transition_id) + ";"
                "foreach (\\Drupal::entityTypeManager()->getStorage('workflow')->loadMultiple() as $wf) {"
                "  $t = $wf->get('transitions')[$tid] ?? NULL;"
                "  if ($t) {"
                "    print json_encode(['id' => $tid, 'workflow' => $wf->id(),"
                "      'label' => (string) ($t['label'] ?? ''),"
                "      'from' => (array) ($t['from'] ?? []),"
                "      'to' => (string) ($t['to'] ?? ''),"
                "      'weight' => (int) ($t['weight'] ?? 0)]);"
                "    return;"
                "  }"
                "}"
                "print json_encode(['error' => 'No transition with id ' . $tid]);"
            )
            result = await drush.run("php:eval", [code])
            payload = _ensure_dict(result)
            if payload.get("error"):
                return payload
            data = payload.get("data")
            if isinstance(data, dict) and data.get("error"):
                return {"error": data["error"], "transition_id": transition_id}
            return data if isinstance(data, dict) else {}
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
        """Create a new moderation transition.

        Not implemented: a transition is configuration inside its workflow, not
        an entity, so it is edited on the workflow and cannot be POSTed as a
        JSON:API resource. `moderation_transition_list` and `workflow_get` read
        the transitions a workflow defines.
        """
        return _absent_entity(
            "workflow_transition",
            "Transitions are configuration inside the `workflow` entity and are "
            "edited on the workflow itself. Read them with "
            "moderation_transition_list.",
        )

    @mcp.tool()
    async def moderation_transition_execute(
        entity_type: str,
        entity_id: str,
        transition_id: str,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        """Execute a moderation transition on an entity.

        Looks the transition up on its workflow and applies its target state to
        the entity, refusing when the entity's current state is not one the
        transition starts from. The old version fetched the transition through
        JSON:API, which has no such resource, so this never ran.
        """
        if not drush:
            return {"error": "Drush not available"}
        try:
            import json as _json

            uid = int(user_id) if user_id else None
            code = (
                "$type = " + _json.dumps(entity_type) + ";"
                "$eid = " + _json.dumps(entity_id) + ";"
                "$tid = " + _json.dumps(transition_id) + ";"
                "$entity = \\Drupal::entityTypeManager()->getStorage($type)->load($eid);"
                "if (!$entity) { print json_encode(['error' => 'No ' . $type . ' with id ' . $eid]); }"
                "elseif (!$entity->hasField('moderation_state')) {"
                "  print json_encode(['error' => $type . ' has no moderation_state field']);"
                "} else {"
                "  $t = NULL;"
                "  foreach (\\Drupal::entityTypeManager()->getStorage('workflow')->loadMultiple() as $wf) {"
                "    $c = $wf->get('transitions')[$tid] ?? NULL;"
                "    if ($c) { $t = $c; break; }"
                "  }"
                "  if (!$t) { print json_encode(['error' => 'No transition with id ' . $tid]); }"
                "  else {"
                "    $current = (string) $entity->get('moderation_state')->value;"
                "    $from = (array) ($t['from'] ?? []);"
                "    if (!in_array('*', $from, TRUE) && !in_array($current, $from, TRUE)) {"
                "      print json_encode(['error' => 'Entity is in state ' . $current"
                "        . ', but transition ' . $tid . ' starts from one of: ' . implode(', ', $from)]);"
                "    } else {"
                "      $to = (string) ($t['to'] ?? '');"
                "      $entity->set('moderation_state', $to);"
                "      " + ("$entity->set('uid', " + str(uid) + ");" if uid else "") + ""
                "      $entity->save();"
                "      print json_encode(['ok' => TRUE, 'transition' => $tid,"
                "        'from' => $current, 'to' => $to]);"
                "    }"
                "  }"
                "}"
            )
            result = await drush.run("php:eval", [code])
            payload = _ensure_dict(result)
            if payload.get("error"):
                return payload
            data = payload.get("data")
            if isinstance(data, dict) and data.get("error"):
                return {"error": data["error"], "transition_id": transition_id}
            return data if isinstance(data, dict) else {}
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
