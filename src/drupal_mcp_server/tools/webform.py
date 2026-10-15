"""Webform tools for Drupal."""

import json
from typing import Any

from fastmcp import FastMCP

from ._utils import ensure_dict as _ensure_dict
from ._utils import php_json, php_text


def _handler_locate_php(handler_id: str, webform_id: str | None) -> str:
    """PHP that resolves a handler id to `$wf` and `$handler`, or explains why not.

    A handler lives inside one webform's configuration and has no id that is
    unique site-wide, so with no `webform_id` given this searches every
    webform. Exactly one match is used; no match, or several, prints an error
    that says what was found instead of guessing. On error the ``return``
    stops the caller's own code from running.

    Existence is tested against `getHandlers()->getInstanceIds()` and never
    through `Webform::getHandler()`, which looks the handler up in the plugin
    collection: an id the collection has never seen reaches
    `initializePlugin()` with an empty configuration and throws
    `PluginNotFoundException`, so asking "is there a handler called X?"
    explodes instead of answering no.
    """
    return (
        "$hid = " + php_text(handler_id) + ";"
        "$wfid = " + php_text(webform_id or "") + ";"
        "$storage = \\Drupal::entityTypeManager()->getStorage('webform');"
        "$all = $storage->loadMultiple();"
        "$wf = NULL; $handler = NULL;"
        "if ($wfid !== '') {"
        "  if (!isset($all[$wfid])) {"
        "    print json_encode(['error' => 'No webform with id ' . $wfid,"
        "      'available' => array_keys($all)]);"
        "    return;"
        "  }"
        "  $wf = $all[$wfid];"
        "  $ids = $wf->getHandlers()->getInstanceIds();"
        "  if (!in_array($hid, $ids, TRUE)) {"
        "    print json_encode(['error' => 'Webform ' . $wfid"
        "      . ' has no handler with id ' . $hid,"
        "      'available' => array_keys($ids)]);"
        "    return;"
        "  }"
        "  $handler = $wf->getHandler($hid);"
        "} else {"
        "  $matches = [];"
        "  foreach ($all as $candidate) {"
        "    if (in_array($hid, $candidate->getHandlers()->getInstanceIds(), TRUE)) {"
        "      $matches[] = $candidate->id();"
        "    }"
        "  }"
        "  if (!$matches) {"
        "    $owned = [];"
        "    foreach ($all as $candidate) {"
        "      foreach ($candidate->getHandlers() as $h) {"
        "        $owned[] = $candidate->id() . ':' . $h->getHandlerId();"
        "      }"
        "    }"
        "    print json_encode(['error' => 'No webform has a handler with id ' . $hid,"
        "      'available' => $owned]);"
        "    return;"
        "  }"
        "  if (count($matches) > 1) {"
        "    print json_encode(['error' => 'Handler id ' . $hid . ' is used by '"
        "      . count($matches) . ' webforms: ' . implode(', ', $matches)"
        "      . '. Pass webform_id to say which one.', 'matches' => $matches]);"
        "    return;"
        "  }"
        "  $wf = $all[$matches[0]];"
        "  $handler = $wf->getHandler($hid);"
        "}"
    )


def _handler_result(
    result: Any, *, webform_id: str | None, handler_id: str
) -> dict[str, Any]:
    """Turn a drush run into a reply, refusing to pass silence off as success."""
    payload = _ensure_dict(result)
    if payload.get("error"):
        return payload
    data = payload.get("data")
    if isinstance(data, dict) and data.get("error"):
        out: dict[str, Any] = {"error": data["error"], "handler_id": handler_id}
        if webform_id:
            out["webform_id"] = webform_id
        for key in ("available", "matches"):
            if data.get(key):
                out[key] = data[key]
        return out
    if not isinstance(data, dict) or "ok" not in data:
        return {
            "error": "Webform did not confirm the change: "
            + json.dumps(payload, default=str)[:200],
            "handler_id": handler_id,
        }
    return data


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

        A handler is a plugin held inside the webform's own configuration --
        there is no `webform_handler` entity and JSON:API cannot POST one.
        This builds the plugin through `plugin.manager.webform.handler` and
        attaches it with `Webform::addWebformHandler()`, which is the same
        sequence Webform's own add-handler form runs.

        `id` is the handler's id *within* the webform (`email_confirmation`,
        not `email`); `handler_type` is the plugin (`email`, `webhook`,
        `auto_save`, ...). `configuration` supplies plugin settings, which are
        merged over the plugin's defaults -- the reply echoes the whole
        resulting configuration so you can see what the defaults filled in.
        """
        if not drush:
            return {"error": "Drush not available"}
        try:
            code = (
                "$hid = " + php_text(id) + ";"
                "$wfid = " + php_text(webform_id) + ";"
                "$type = " + php_text(handler_type) + ";"
                "$label = " + php_text(label) + ";"
                "$settings = " + php_json(configuration or {}) + ";"
                "$storage = \\Drupal::entityTypeManager()->getStorage('webform');"
                "$all = $storage->loadMultiple();"
                "if (!isset($all[$wfid])) {"
                "  print json_encode(['error' => 'No webform with id ' . $wfid,"
                "    'available' => array_keys($all)]);"
                "  return;"
                "}"
                "$wf = $all[$wfid];"
                "$manager = \\Drupal::service('plugin.manager.webform.handler');"
                "if (!$manager->getDefinition($type, FALSE)) {"
                "  print json_encode(['error' => 'This site has no webform '"
                "    . 'handler plugin ' . $type . '.',"
                "    'available' => array_keys($manager->getDefinitions())]);"
                "  return;"
                "}"
                # Webform::getHandler() throws on an id it has never seen
                # instead of returning NULL, so the duplicate check reads the
                # plugin collection's own id list.
                "$ids = $wf->getHandlers()->getInstanceIds();"
                "if (in_array($hid, $ids, TRUE)) {"
                "  print json_encode(['error' => 'Webform ' . $wfid"
                "    . ' already has a handler with id ' . $hid,"
                "    'available' => array_keys($ids)]);"
                "  return;"
                "}"
                "try {"
                "  $handler = $manager->createInstance($type, ["
                "    'id' => $type, 'handler_id' => $hid, 'label' => $label,"
                "    'notes' => '', 'status' => TRUE,"
                "    'weight' => count($wf->getHandlers()),"
                "    'conditions' => [], 'settings' => $settings]);"
                "  $wf->addWebformHandler($handler);"
                "} catch (\\Throwable $e) {"
                "  print json_encode(['error' => $e->getMessage()]);"
                "  return;"
                "}"
                "print json_encode(['ok' => TRUE, 'id' => (string) $hid,"
                "  'webform_id' => (string) $wfid, 'type' => (string) $type,"
                "  'handler' => $handler->getConfiguration()]);"
            )
            result = await drush.run("php:eval", [code])
            return _handler_result(result, webform_id=webform_id, handler_id=id)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def webform_handler_update(
        handler_id: str,
        label: str | None = None,
        configuration: dict[str, Any] | None = None,
        webform_id: str | None = None,
    ) -> dict[str, Any]:
        """Update a webform handler.

        Handlers have no entity id of their own, so this finds the webform
        that owns `handler_id` and writes back through
        `Webform::updateWebformHandler()`. Pass `webform_id` to skip the
        search; without it, a handler id used by more than one webform is an
        error naming them rather than a guess.

        `configuration` keys are replaced as a whole and keys you leave out
        keep their current value, so you can change one setting without
        resending the rest.
        """
        if not drush:
            return {"error": "Drush not available"}
        if label is None and configuration is None:
            return {
                "error": "Nothing to change: pass `label`, `configuration`, or both.",
                "handler_id": handler_id,
            }
        try:
            code = (
                _handler_locate_php(handler_id, webform_id)
                + "$cfg = $handler->getConfiguration();"
                + ("$cfg['label'] = " + php_text(label) + ";" if label is not None else "")
                + (
                    "$cfg['settings'] = array_replace($cfg['settings'], "
                    + php_json(configuration or {})
                    + ");"
                    if configuration is not None
                    else ""
                )
                + "try {"
                "  $handler->setConfiguration($cfg);"
                "  $wf->updateWebformHandler($handler);"
                "} catch (\\Throwable $e) {"
                "  print json_encode(['error' => $e->getMessage()]);"
                "  return;"
                "}"
                "print json_encode(['ok' => TRUE, 'id' => (string) $hid,"
                "  'webform_id' => $wf->id(), 'handler' => $handler->getConfiguration()]);"
            )
            result = await drush.run("php:eval", [code])
            return _handler_result(result, webform_id=webform_id, handler_id=handler_id)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def webform_handler_delete(
        handler_id: str,
        webform_id: str | None = None,
    ) -> dict[str, Any]:
        """Delete a webform handler from its webform.

        Removes it the way Webform's own delete form does -- through
        `Webform::deleteWebformHandler()`, which also runs the plugin's
        teardown. The webform's other handlers are left alone.
        """
        if not drush:
            return {"error": "Drush not available"}
        try:
            code = (
                _handler_locate_php(handler_id, webform_id)
                + "try {"
                "  $wf->deleteWebformHandler($handler);"
                "} catch (\\Throwable $e) {"
                "  print json_encode(['error' => $e->getMessage()]);"
                "  return;"
                "}"
                "print json_encode(['ok' => TRUE, 'id' => (string) $hid,"
                "  'webform_id' => $wf->id(), 'deleted' => TRUE,"
                "  'remaining' => count($wf->getHandlers()->getInstanceIds())]);"
            )
            result = await drush.run("php:eval", [code])
            return _handler_result(result, webform_id=webform_id, handler_id=handler_id)
        except Exception as e:
            return {"error": str(e)}

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
