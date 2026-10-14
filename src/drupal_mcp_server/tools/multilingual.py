"""Multilingual workflow tools for Drupal."""

from typing import Any

from fastmcp import FastMCP

from ._utils import absent_entity as _absent_entity
from ._utils import ensure_dict as _ensure_dict


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
        """List interface translations.

        Not implemented: Drupal keeps interface translations in Locale's own
        storage rather than as a JSON:API entity, so there is no
        `interface_translation` resource to page through. `drush locale:export`
        writes them out as a .po file, which is the supported way to read them.
        """
        return _absent_entity(
            "interface_translation",
            "Locale stores interface translations in its own storage, not as an "
            "entity. Use drush locale:export to read them, or locale:import to "
            "load a .po file.",
        )

    @mcp.tool()
    async def interface_translation_add(
        source: str,
        langcode: str,
        translation: str,
        context: str = "",
    ) -> dict[str, Any]:
        """Add an interface translation.

        Not implemented. The `locale:translate:add` command this used to run
        does not exist -- Drush offers `locale:import` and `locale:export`, and
        a single string is translated through Locale's own API rather than a
        command.
        """
        return _absent_entity(
            "interface_translation",
            "There is no locale:translate:add command. Use drush locale:import "
            "with a .po file to add translations.",
        )

    @mcp.tool()
    async def interface_translation_update(
        source: str,
        langcode: str,
        translation: str,
        context: str = "",
    ) -> dict[str, Any]:
        """Update an interface translation.

        Not implemented; `locale:translate:update` does not exist. See
        `interface_translation_add`.
        """
        return _absent_entity(
            "interface_translation",
            "There is no locale:translate:update command. Use drush locale:import "
            "with a .po file to update translations.",
        )

    @mcp.tool()
    async def interface_translation_delete(
        source: str,
        langcode: str,
        context: str = "",
    ) -> dict[str, Any]:
        """Delete an interface translation.

        Not implemented; `locale:translate:delete` does not exist. See
        `interface_translation_add`.
        """
        return _absent_entity(
            "interface_translation",
            "There is no locale:translate:delete command. Translations are "
            "removed by re-importing a .po file without them.",
        )

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
        `node_type/article` or `field_config/field.field.node.article.body`.
        `config_translation_list` shows which entity types this site can
        translate. `translation` is a flat map of property to translated value.

        The old version ran `config:translation:add`, which is not a Drush
        command -- Drush has no translation command category at all -- so this
        failed every time. Drupal stores a config entity's translation as an
        entity translation, so that is what is written.

        A config entity must be translated as a whole entity: its translation
        lives on the entity, not in a standalone object, which is why the
        single-name form this used to take cannot work.
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
                "$entity = \\Drupal::entityTypeManager()->getStorage($type)->load($id);"
                "if (!$entity) {"
                "  print json_encode(['error' => 'No ' . $type . ' with id ' . $id]);"
                "} elseif (!($entity instanceof \\Drupal\\Core\\Entity\\TranslatableInterface)) {"
                "  print json_encode(['error' => $type . ' does not support translation']);"
                "} else {"
                "  $t = $entity->hasTranslation($lang) ? $entity->getTranslation($lang)"
                "       : $entity->addTranslation($lang, []);"
                "  foreach ((array) $values as $k => $v) { $t->set($k, $v); }"
                "  $t->save();"
                "  print json_encode(['ok' => TRUE, 'entity_type' => $type,"
                "                     'id' => $id, 'langcode' => $lang]);"
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
