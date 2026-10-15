"""Multilingual workflow tools for Drupal."""

import json
from typing import Any

from fastmcp import FastMCP

from ._utils import ensure_dict as _ensure_dict
from ._utils import php_json, php_text, validate_pagination


def _locale_write_php(
    action: str, source: str, langcode: str, translation: str, context: str
) -> str:
    """Build the PHP that adds, updates or deletes one interface translation.

    All three go through `locale.storage` rather than a Drush command,
    because Drush has no `locale:translate:*` command to call: the storage
    is what `locale:import` writes through. `action` is `add`, `update`
    or `delete`.
    """
    return (
        "$action = " + php_text(action) + ";"
        "$source = " + php_text(source) + ";"
        "$lang = " + php_text(langcode) + ";"
        "$text = " + php_text(translation) + ";"
        "$ctx = " + php_text(context) + ";"
        "$storage = \\Drupal::service('locale.storage');"
        "$find = ['source' => $source, 'context' => $ctx];"
        "$str = $storage->findString($find);"
        "$srcLabel = '\"' . $source . '\"' . ($ctx === '' ? '' : ' (context \"' . $ctx . '\")');"
        "$source_created = FALSE;"
        "if (!$str) {"
        "  if ($action === 'update') {"
        "    print json_encode(['error' => 'There is no source string ' . $srcLabel"
        "      . '. Use interface_translation_add to create it.']);"
        "    return;"
        "  }"
        "  $str = $storage->createString($find);"
        "  $storage->save($str);"
        "  $source_created = TRUE;"
        "}"
        "$lid = (int) $str->getId();"
        "$cur = $storage->findTranslation(['lid' => $lid, 'language' => $lang]);"
        "$exists = $cur && (string) $cur->language === (string) $lang;"
        "if ($action !== 'add' && !$exists) {"
        "  $hint = $action === 'update'"
        "    ? ' Use interface_translation_add to create it.' : '';"
        "  print json_encode(['error' => 'There is no ' . $lang . ' translation for '"
        "    . $srcLabel . '.' . $hint, 'lid' => $lid]);"
        "  return;"
        "}"
        "if ($action === 'delete') {"
        "  $storage->deleteTranslations(['lid' => $lid, 'language' => $lang]);"
        "} else {"
        "  if ($exists) {"
        "    $cur->setString($text);"
        "    $cur->setCustomized(TRUE);"
        "    $storage->save($cur);"
        "  } else {"
        "    $storage->save($storage->createTranslation(["
        "      'lid' => $lid, 'language' => $lang, 'translation' => $text,"
        "      'customized' => LOCALE_CUSTOMIZED]));"
        "  }"
        "}"
        # `_locale_refresh_translations()` is what Drupal's own translate form
        # calls after a save: it refreshes the JavaScript translations and
        # dispatches `LocaleEvents::SAVE_TRANSLATION`, whose subscriber
        # invalidates the `locale` cache tag -- and every LocaleLookup entry in
        # cache.default is tagged `locale`, so the cached strings go with it.
        # Without this the write lands in locales_target but pages keep serving
        # the old text until an unrelated cache clear.
        "if (function_exists('_locale_refresh_translations')) {"
        "  _locale_refresh_translations([$lang], [$lid]);"
        "}"
        "\\Drupal::service('string_translator.locale.lookup')->reset();"
        "$out = ['ok' => TRUE, 'action' => $action, 'lid' => $lid,"
        "  'langcode' => (string) $lang, 'source' => $source, 'context' => $ctx,"
        "  'source_created' => $source_created];"
        "if ($action === 'delete') { $out['deleted'] = TRUE; }"
        "else { $out['created'] = !$exists; $out['translation'] = $text; }"
        "print json_encode($out);"
    )


def _locale_write_result(result: Any, source: str, langcode: str) -> dict[str, Any]:
    """Turn a drush run into a reply, refusing to pass silence off as success."""
    payload = _ensure_dict(result)
    if payload.get("error"):
        return payload
    data = payload.get("data")
    if isinstance(data, dict) and data.get("error"):
        out: dict[str, Any] = {
            "error": data["error"],
            "source": source,
            "langcode": langcode,
        }
        if data.get("lid") is not None:
            out["lid"] = data["lid"]
        return out
    if not isinstance(data, dict) or "ok" not in data:
        return {
            "error": "Locale did not confirm the write: "
            + json.dumps(payload, default=str)[:200],
            "source": source,
            "langcode": langcode,
        }
    return data


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")
    jsonapi = deps.get("jsonapi_client")

    @mcp.tool()
    async def language_list(
        filters: dict[str, Any] | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List all languages."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if filters:
                for key, value in filters.items():
                    params[f"filter[{key}]"] = str(value)
            
            result = await jsonapi.get_resource("configurable_language", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def language_get(
        langcode: str,
        include: str = "",
    ) -> dict[str, Any]:
        """Get a single language by langcode."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("configurable_language", langcode, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def language_add(
        langcode: str,
        name: str,
        direction: str = "ltr",
        weight: int = 0,
    ) -> dict[str, Any]:
        """Add a new language."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("language:add", [langcode, "--name", name, "--direction", direction, "--weight", str(weight)])
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def language_enable(
        langcode: str,
    ) -> dict[str, Any]:
        """Enable a language."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("language:enable", [langcode])
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def language_disable(
        langcode: str,
    ) -> dict[str, Any]:
        """Disable a language."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("language:disable", [langcode])
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def language_delete(
        langcode: str,
    ) -> dict[str, Any]:
        """Delete a language."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("language:delete", [langcode])
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def content_translation_enable(
        entity_type: str,
        bundle: str | None = None,
    ) -> dict[str, Any]:
        """Enable content translation for entity type/bundle."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            entity = f"{entity_type}"
            if bundle:
                entity += f".{bundle}"
            result = await drush.run("config:set", ["content_translation.settings", "entity." + entity, "true"])
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def translation_status(
        entity_type: str,
        entity_id: str,
    ) -> dict[str, Any]:
        """Get translation status for an entity."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.get_by_id(entity_type, entity_id, params={"include": "translations"})
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def translation_add(
        entity_type: str,
        entity_id: str,
        langcode: str,
        fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Add translation for an entity."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            # Get source entity
            entity = await jsonapi.get_by_id(entity_type, entity_id)
            entity = _ensure_dict(entity)
            if entity.get("error"):
                return entity
            
            # Create translation
            translation_data = {
                "type": entity_type,
                "id": entity_id,
                "langcode": langcode,
            }
            if fields:
                translation_data.update(fields)
            
            result = await jsonapi.create_resource(entity_type, translation_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def translation_update(
        entity_type: str,
        entity_id: str,
        langcode: str,
        fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update translation for an entity."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            translation_id = f"{entity_id}:{langcode}"
            update_data = {"id": translation_id, "type": entity_type}
            if fields:
                update_data.update(fields)
            
            result = await jsonapi.update_resource(entity_type, translation_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def interface_translation_list(
        langcode: str | None = None,
        filters: dict[str, Any] | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List the interface translations Drupal holds.

        Locale does not store translations as entities, so there is no
        `interface_translation` resource to page through: they live in Locale's
        own storage, joined from each source string to its translation in a
        language -- which is where `drush locale:export` reads them from too.

        `langcode` narrows the list to one language; left out, every language
        is listed and each row says which one it is. `filters` accepts `search`
        (a substring of the source text) and `context` (the source context,
        matched exactly). Only translated strings are returned: an untranslated
        source is not a translation. `count` is the total that matched, before
        paging.
        """
        if not drush:
            return {"error": "Drush not available"}
        pag_err = validate_pagination(page_limit, page_offset)
        if pag_err:
            return pag_err
        try:
            f = filters or {}
            unknown = sorted(set(f) - {"search", "context"})
            if unknown:
                return {
                    "error": "Unsupported filter(s): "
                    + ", ".join(unknown)
                    + ". interface_translation_list accepts `search` (a substring "
                    "of the source text) and `context` (matched exactly).",
                    "langcode": langcode,
                }
            # Scalars only. A JSON object is not a PHP array literal -- `{}`
            # and `{"k": 1}` are both parse errors there -- so the filter values
            # are pulled apart here instead of being embedded as JSON.
            search = str(f.get("search") or "")
            has_ctx = "context" in f
            ctx = str(f.get("context") or "")
            code = (
                "$lang = " + php_json(langcode) + ";"
                "$limit = " + str(int(page_limit)) + ";"
                "$offset = " + str(int(page_offset)) + ";"
                "$search = " + php_text(search) + ";"
                "$ctx = " + (php_text(ctx) if has_ctx else "NULL") + ";"
                "$storage = \\Drupal::service('locale.storage');"
                "$conditions = ['translated' => TRUE];"
                "$options = [];"
                "if ($lang) { $conditions['language'] = $lang; }"
                "if ($ctx !== NULL) { $conditions['context'] = $ctx; }"
                "if ($search !== '') { $options['filters'] = ['source' => $search]; }"
                "$options['pager limit'] = $offset + $limit;"
                "$out = [];"
                "foreach ($storage->getTranslations($conditions, $options) as $r) {"
                "  $out[] = ['lid' => (int) ($r->lid ?? 0),"
                "    'source' => (string) ($r->source ?? ''),"
                "    'context' => (string) ($r->context ?? ''),"
                "    'language' => (string) ($r->language ?? ''),"
                "    'translation' => (string) ($r->translation ?? ''),"
                "    'customized' => (bool) ($r->customized ?? FALSE)];"
                "}"
                "$db = \\Drupal::database();"
                "$q = $db->select('locales_source', 's');"
                "$q->innerJoin('locales_target', 't',"
                "  $lang ? 't.lid = s.lid AND t.language = :ilang' : 't.lid = s.lid',"
                "  $lang ? [':ilang' => $lang] : []);"
                "if ($ctx !== NULL) { $q->condition('s.context', $ctx, '='); }"
                "if ($search !== '') {"
                "  $q->condition('s.source', '%' . $db->escapeLike($search) . '%', 'LIKE');"
                "}"
                "print json_encode(['count' => (int) $q->countQuery()->execute()->fetchField(),"
                "  'translations' => $out]);"
            )
            result = await drush.run("php:eval", [code])
            payload = _ensure_dict(result)
            if payload.get("error"):
                return payload
            data = payload.get("data")
            if not isinstance(data, dict) or "translations" not in data:
                # An empty list here would read as "no translations" and hide
                # a drush or PHP failure, which is how the transition list
                # once reported zero transitions on a workflow that had five.
                return {
                    "error": "Locale did not return a translation list: "
                    + json.dumps(payload, default=str)[:200],
                    "langcode": langcode,
                }
            rows = data.get("translations") or []
            start = int(page_offset)
            return {
                "langcode": langcode,
                "count": int(data.get("count") or 0),
                "translations": rows[start:start + int(page_limit)],
            }
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def interface_translation_add(
        source: str,
        langcode: str,
        translation: str,
        context: str = "",
    ) -> dict[str, Any]:
        """Add an interface translation for one source string.

        Written through Locale's own string storage -- `createString()` /
        `createTranslation()` plus `save()` -- which is what `locale:import`
        does with a .po file, one entry at a time. There is no
        `locale:translate:*` command to run instead.

        If the source string is not one Drupal has already collected, it is
        created too and the reply says so: a translation nobody will ever look
        up is worth knowing about. The locale lookup cache is invalidated, so
        the new text is visible without a cache rebuild.
        """
        if not drush:
            return {"error": "Drush not available"}
        try:

            code = _locale_write_php("add", source, langcode, translation, context)
            result = await drush.run("php:eval", [code])
            return _locale_write_result(result, source, langcode)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def interface_translation_update(
        source: str,
        langcode: str,
        translation: str,
        context: str = "",
    ) -> dict[str, Any]:
        """Change an existing interface translation.

        Same storage as `interface_translation_add`, but this one refuses to
        invent anything: an unknown source string, or a source with no
        translation in `langcode`, is an error that says which of those it is
        and points at `interface_translation_add`. The string is marked
        customized so a later `locale:import` does not overwrite it.
        """
        if not drush:
            return {"error": "Drush not available"}
        try:
            code = _locale_write_php("update", source, langcode, translation, context)
            result = await drush.run("php:eval", [code])
            return _locale_write_result(result, source, langcode)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def interface_translation_delete(
        source: str,
        langcode: str,
        context: str = "",
    ) -> dict[str, Any]:
        """Remove an interface translation from one language.

        Drops the row from `locales_target` for this source and language; the
        source string itself stays, because it is Drupal's own string and other
        languages still use it. There is no `locale:translate:delete` command,
        and re-importing a .po file without the entry is no longer the only way
        to do this.
        """
        if not drush:
            return {"error": "Drush not available"}
        try:
            code = _locale_write_php("delete", source, langcode, "", context)
            result = await drush.run("php:eval", [code])
            return _locale_write_result(result, source, langcode)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def config_translation_list(
        page_limit: int = 50,
    ) -> dict[str, Any]:
        """List the config objects that support translation.

        There is no `config_translation` resource in JSON:API, because Drupal
        does not store config translations as entities: a translation belongs to
        the config object that declares a translation mapping. Asking JSON:API
        for a resource that cannot exist returned a 404 that read exactly like
        a missing module, so the tool looked uninstalled rather than wrong.

        Each mapping is returned with the entity type it translates. The
        mapping's own config-name list is empty until Drupal builds it inside
        the translation form, so it is not reported here -- the id and the
        entity type are what `config_translation_add` needs.
        """
        if not drush:
            return {"error": "Drush not available"}
        try:
            limit = max(1, int(page_limit))
            code = (
                "$m = \\Drupal::service('plugin.manager.config_translation.mapper');"
                "$ids = array_slice(array_keys($m->getDefinitions()), 0, " + str(limit) + ");"
                "$out = [];"
                "foreach ($ids as $id) {"
                "  $d = $m->getDefinition($id);"
                "  $out[$id] = ['entity_type' => $d['entity_type'] ?? '',"
                "               'base_entity_type' => $d['base_entity_type'] ?? ''];"
                "}"
                "print json_encode($out);"
            )
            result = await drush.run("php:eval", [code])
            payload = _ensure_dict(result)
            if payload.get("error"):
                return payload
            data = payload.get("data") or {}
            return {"mappings": data, "count": len(data)}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def config_translation_add(
        config_name: str,
        langcode: str,
        translation: dict[str, Any],
    ) -> dict[str, Any]:
        """Translate a config entity.

        `config_name` is `{entity_type}/{entity_id}`, for example
        `node_type/article`. `config_translation_list` shows which entity
        types this site can translate. `translation` is a flat map of
        property to translated value.

        A config entity is not a translatable entity. There is no
        `TranslatableInterface` to call, no `addTranslation()`, and no
        `config:translation:add` Drush command -- which is what this tool
        tried, twice, both failing every time. Drupal keeps a config
        translation as a *language config override*: the same config object,
        overridden per language. So the entity type is resolved through the
        config translation mapper to the config object it is stored as, and
        that object's override for the target language is what gets written.
        """
        if not drush:
            return {"error": "Drush not available"}
        try:
            import json as _json

            if "/" not in config_name:
                return {
                    "error": (
                        f"{config_name!r} is not a config entity reference. Use "
                        "'{entity_type}/{entity_id}', for example "
                        "'node_type/article'. Call config_translation_list to "
                        "see what this site can translate."
                    )
                }
            entity_type, _, entity_id = config_name.partition("/")
            values_json = _json.dumps(translation)
            # No shell is involved: the code reaches drush as one argv token,
            # so PHP quotes are literal and nothing needs escaping.
            code = (
                "$type = " + _json.dumps(entity_type) + ";"
                "$id = " + _json.dumps(entity_id) + ";"
                "$lang = " + _json.dumps(langcode) + ";"
                "$values = json_decode(" + _json.dumps(values_json) + ", TRUE);"
                "$mgr = \\Drupal::service('plugin.manager.config_translation.mapper');"
                "$plugin = NULL;"
                "foreach ($mgr->getDefinitions() as $pid => $def) {"
                "  if (($def['entity_type'] ?? '') === $type) { $plugin = $pid; break; }"
                "}"
                "$entity = NULL;"
                "if (\\Drupal::entityTypeManager()->hasDefinition($type)) {"
                "  $entity = \\Drupal::entityTypeManager()->getStorage($type)->load($id);"
                "}"
                "if (!$plugin) {"
                "  print json_encode(['error' => 'No config translation mapper for '"
                "    . $type . '. Call config_translation_list for what this site"
                " can translate.']);"
                "} elseif (!$entity) {"
                "  print json_encode(['error' => 'No ' . $type . ' with id ' . $id]);"
                "} else {"
                "  $mapper = $mgr->createInstance($plugin);"
                "  $mapper->setEntity($entity);"
                "  $written = [];"
                "  foreach ($mapper->getConfigNames() as $name) {"
                "    $override = \\Drupal::languageManager()"
                "      ->getLanguageConfigOverride($lang, $name);"
                "    foreach ((array) $values as $k => $v) { $override->set($k, $v); }"
                "    $override->save();"
                "    $written[] = $name;"
                "  }"
                "  print json_encode(['ok' => TRUE, 'entity_type' => $type,"
                "                     'id' => $id, 'langcode' => $lang,"
                "                     'config' => $written]);"
                "}"
            )
            result = await drush.run("php:eval", [code])
            payload = _ensure_dict(result)
            if payload.get("error"):
                return payload
            data = payload.get("data")
            if isinstance(data, dict) and data.get("error"):
                return {"error": data["error"], "config_name": config_name}
            return {"config_name": config_name, "langcode": langcode, **(data or {})}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def language_negotiation_get(
    ) -> dict[str, Any]:
        """Get language negotiation configuration."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("config:get", ["language.negotiation"])
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def language_negotiation_set(
        method: str,
        weight: int = 0,
    ) -> dict[str, Any]:
        """Set language negotiation method."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("config:set", ["language.negotiation", method, str(weight)])
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}
