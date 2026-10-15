"""Content moderation workflow tools for Drupal."""

from typing import Any

from fastmcp import FastMCP

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
        for JSON:API to list. They are read from the workflow's workflow-type
        plugin (`WorkflowTypeInterface::getTransitions()`), which is where
        Drupal keeps them.

        Every workflow is read when `workflow_id` is left out. Naming a
        workflow that does not exist answers an error listing the ones this
        site has, rather than an empty list that reads as "no transitions".
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
                "$all = \\Drupal::entityTypeManager()->getStorage('workflow')->loadMultiple();"
                "$ids = " + _json.dumps(ids) + ";"
                "if ($ids) {"
                "  $missing = array_values(array_diff($ids, array_keys($all)));"
                "  if ($missing) {"
                "    print json_encode(['error' => 'No workflow with id '"
                "      . implode(', ', $missing), 'available' => array_keys($all)]);"
                "    return;"
                "  }"
                "  $all = array_intersect_key($all, array_flip($ids));"
                "}"
                "$out = [];"
                "foreach ($all as $wf) {"
                "  $wt = $wf->getTypePlugin();"
                "  if (!$wt) { continue; }"
                "  foreach ($wt->getTransitions() as $tid => $t) {"
                "    $to = $t->to();"
                "    $out[] = ['id' => (string) $tid, 'workflow' => $wf->id(),"
                "      'label' => (string) $t->label(),"
                "      'from' => array_keys((array) $t->from()),"
                "      'to' => (string) $to->id(),"
                "      'weight' => (int) $t->weight()];"
                "  }"
                "}"
                "print json_encode(array_values($out));"
            )
            result = await drush.run("php:eval", [code])
            payload = _ensure_dict(result)
            if payload.get("error"):
                return payload
            data = payload.get("data")
            if isinstance(data, dict) and data.get("error"):
                return data
            rows = data if isinstance(data, list) else []
            start = int(page_offset)
            window = rows[start:start + int(page_limit)]
            return {"count": len(rows), "transitions": window}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def moderation_transition_get(transition_id: str, include: str = "") -> dict[str, Any]:
        """Get a single moderation transition by ID.

        Transitions belong to a workflow rather than being entities, so this
        searches every workflow's transitions for the named one. Pass
        `include=states` to attach the states of the workflow that owns it --
        transitions have no JSON:API relationships to include.
        """
        if not drush:
            return {"error": "Drush not available"}
        try:
            import json as _json

            want_states = "state" in include.lower()
            code = (
                "$tid = " + _json.dumps(transition_id) + ";"
                "$all = \\Drupal::entityTypeManager()->getStorage('workflow')->loadMultiple();"
                "foreach ($all as $wf) {"
                "  $wt = $wf->getTypePlugin();"
                "  if (!$wt || !$wt->hasTransition($tid)) { continue; }"
                "  $t = $wt->getTransition($tid);"
                "  $to = $t->to();"
                "  $row = ['id' => (string) $tid, 'workflow' => $wf->id(),"
                "    'label' => (string) $t->label(),"
                "    'from' => array_keys((array) $t->from()),"
                "    'to' => (string) $to->id(),"
                "    'weight' => (int) $t->weight()];"
                "  if (" + ("TRUE" if want_states else "FALSE") + ") {"
                "    $states = [];"
                "    foreach ($wt->getStates() as $sid => $s) {"
                "      $states[] = ['id' => (string) $sid, 'label' => (string) $s->label()];"
                "    }"
                "    $row['states'] = $states;"
                "  }"
                "  print json_encode($row);"
                "  return;"
                "}"
                "$known = [];"
                "foreach ($all as $wf) {"
                "  $wt = $wf->getTypePlugin();"
                "  if ($wt) { $known = array_merge($known, array_keys($wt->getConfiguration()['transitions'] ?? [])); }"
                "}"
                "print json_encode(['error' => 'No transition with id ' . $tid,"
                "  'available' => array_values(array_unique($known))]);"
            )
            result = await drush.run("php:eval", [code])
            payload = _ensure_dict(result)
            if payload.get("error"):
                return payload
            data = payload.get("data")
            if isinstance(data, dict) and data.get("error"):
                return {"error": data["error"], "transition_id": transition_id,
                        "available": data.get("available", [])}
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
        """Create a new moderation transition on a workflow.

        Transitions are configuration inside the `workflow` entity, so they
        cannot be POSTed as a JSON:API resource. This adds one the way
        Drupal's own transition form does: through
        `WorkflowTypeInterface::addTransition()` and a save of the workflow,
        which writes the change back into the workflow's configuration.

        Both the origin states and the target state must already exist in the
        workflow; an error names the ones that do not and lists the states the
        workflow does have. `weight` defaults to 0, which places the transition
        first -- pass a higher number to append it.
        """
        if not drush:
            return {"error": "Drush not available"}
        if not from_states:
            return {
                "error": "from_states must name at least one state this "
                "transition starts from.",
                "workflow_id": workflow_id,
            }
        try:
            import json as _json

            code = (
                "$wfid = " + _json.dumps(workflow_id) + ";"
                "$tid = " + _json.dumps(transition_id) + ";"
                "$label = " + _json.dumps(label) + ";"
                "$from = " + _json.dumps(list(from_states)) + ";"
                "$to = " + _json.dumps(to_state) + ";"
                "$weight = " + str(int(weight)) + ";"
                "$all = \\Drupal::entityTypeManager()->getStorage('workflow')->loadMultiple();"
                "if (!isset($all[$wfid])) {"
                "  print json_encode(['error' => 'No workflow with id ' . $wfid,"
                "    'available' => array_keys($all)]);"
                "  return;"
                "}"
                "$wf = $all[$wfid];"
                "$wt = $wf->getTypePlugin();"
                "if (!$wt) { print json_encode(['error' => 'Workflow ' . $wfid . ' has no workflow type']); return; }"
                "$states = [];"
                "foreach ($wt->getStates() as $sid => $s) { $states[] = (string) $sid; }"
                "if ($wt->hasTransition($tid)) {"
                "  print json_encode(['error' => 'Workflow ' . $wfid"
                "    . ' already has a transition ' . $tid,"
                "    'available' => array_keys($wt->getConfiguration()['transitions'] ?? [])]);"
                "  return;"
                "}"
                "$missing = array_values(array_diff(array_merge((array) $from, [$to]), $states));"
                "if ($missing) {"
                "  print json_encode(['error' => 'No state ' . implode(', ', $missing)"
                "    . ' in workflow ' . $wfid, 'available_states' => $states]);"
                "  return;"
                "}"
                "try {"
                "  $wt->addTransition($tid, $label, (array) $from, $to);"
                "  $wt->setTransitionWeight($tid, $weight);"
                "} catch (\\InvalidArgumentException $e) {"
                "  print json_encode(['error' => $e->getMessage()]);"
                "  return;"
                "}"
                "try { $wf->save(); } catch (\\Throwable $e) {"
                "  print json_encode(['error' => $e->getMessage()]);"
                "  return;"
                "}"
                "$t = $wt->getTransition($tid);"
                "print json_encode(['ok' => TRUE, 'id' => (string) $tid,"
                "  'workflow' => (string) $wfid, 'label' => (string) $t->label(),"
                "  'from' => array_keys((array) $t->from()),"
                "  'to' => (string) $t->to()->id(),"
                "  'weight' => (int) $t->weight()]);"
            )
            result = await drush.run("php:eval", [code])
            payload = _ensure_dict(result)
            if payload.get("error"):
                return payload
            data = payload.get("data")
            if isinstance(data, dict) and data.get("error"):
                out: dict[str, Any] = {
                    "error": data["error"],
                    "workflow_id": workflow_id,
                    "transition_id": transition_id,
                }
                if data.get("available"):
                    out["available"] = data["available"]
                if data.get("available_states"):
                    out["available_states"] = data["available_states"]
                return out
            return data if isinstance(data, dict) else {}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def moderation_transition_delete(
        workflow_id: str,
        transition_id: str,
    ) -> dict[str, Any]:
        """Delete a moderation transition from a workflow.

        The counterpart of `moderation_transition_create`: a transition is
        configuration inside its workflow, so this removes it through
        `WorkflowTypeInterface::deleteTransition()` and saves the workflow,
        exactly as Drupal's own delete form does. The reply reports how many
        transitions the workflow has left, and warns when that was the last
        one -- a workflow with no transitions cannot move content at all.
        """
        if not drush:
            return {"error": "Drush not available"}
        try:
            import json as _json

            code = (
                "$wfid = " + _json.dumps(workflow_id) + ";"
                "$tid = " + _json.dumps(transition_id) + ";"
                "$all = \\Drupal::entityTypeManager()->getStorage('workflow')->loadMultiple();"
                "if (!isset($all[$wfid])) {"
                "  print json_encode(['error' => 'No workflow with id ' . $wfid,"
                "    'available' => array_keys($all)]);"
                "  return;"
                "}"
                "$wf = $all[$wfid];"
                "$wt = $wf->getTypePlugin();"
                "if (!$wt || !$wt->hasTransition($tid)) {"
                "  $known = []; foreach ($all as $w) {"
                "    $t2 = $w->getTypePlugin();"
                "    if ($t2) { $known = array_merge($known, array_keys($t2->getConfiguration()['transitions'] ?? [])); }"
                "  }"
                "  print json_encode(['error' => 'Workflow ' . $wfid"
                "    . ' has no transition ' . $tid, 'available' => array_values(array_unique($known))]);"
                "  return;"
                "}"
                "$remaining = array_diff_key($wt->getConfiguration()['transitions'] ?? [], [$tid => TRUE]);"
                "$wt->deleteTransition($tid);"
                "try { $wf->save(); } catch (\\Throwable $e) {"
                "  print json_encode(['error' => $e->getMessage()]);"
                "  return;"
                "}"
                "$out = ['ok' => TRUE, 'id' => (string) $tid,"
                "  'workflow' => (string) $wfid, 'remaining' => count($remaining)];"
                "if (!$remaining) {"
                "  $out['warning'] = 'That was the last transition: ' . $wfid"
                "    . ' now has none, so content in it cannot be moderated"
                "    . until one is added.';"
                "}"
                "print json_encode($out);"
            )
            result = await drush.run("php:eval", [code])
            payload = _ensure_dict(result)
            if payload.get("error"):
                return payload
            data = payload.get("data")
            if isinstance(data, dict) and data.get("error"):
                out: dict[str, Any] = {
                    "error": data["error"],
                    "workflow_id": workflow_id,
                    "transition_id": transition_id,
                }
                if data.get("available"):
                    out["available"] = data["available"]
                return out
            return data if isinstance(data, dict) else {}
        except Exception as e:
            return {"error": str(e)}

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
                "    $wt = $wf->getTypePlugin();"
                "    if ($wt && $wt->hasTransition($tid)) { $t = $wt->getTransition($tid); break; }"
                "  }"
                "  if (!$t) { print json_encode(['error' => 'No transition with id ' . $tid]); }"
                "  else {"
                "    $current = (string) $entity->get('moderation_state')->value;"
                "    $from = array_keys((array) $t->from());"
                "    if (!in_array('*', $from, TRUE) && !in_array($current, $from, TRUE)) {"
                "      print json_encode(['error' => 'Entity is in state ' . $current"
                "        . ', but transition ' . $tid . ' starts from one of: ' . implode(', ', $from)]);"
                "    } else {"
                "      $to = (string) $t->to()->id();"
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
