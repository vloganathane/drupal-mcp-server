"""Multilingual workflow tools for Drupal."""

from typing import Any

from fastmcp import FastMCP

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
            
            result = await jsonapi.get_resource("language", params)
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
            result = await jsonapi.get_by_id("language", langcode, params=params if params else None)
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
        """List interface translations."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            
            if langcode:
                params["filter[langcode]"] = langcode
            if filters:
                for key, value in filters.items():
                    params[f"filter[{key}]"] = str(value)
            
            result = await jsonapi.get_resource("interface_translation", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def interface_translation_add(
        source: str,
        langcode: str,
        translation: str,
        context: str = "",
    ) -> dict[str, Any]:
        """Add interface translation."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["locale:translate:add", source, langcode, translation]
            if context:
                cmd.extend(["--context", context])
            result = await drush.run(*cmd)
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def interface_translation_update(
        source: str,
        langcode: str,
        translation: str,
        context: str = "",
    ) -> dict[str, Any]:
        """Update interface translation."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["locale:translate:update", source, langcode, translation]
            if context:
                cmd.extend(["--context", context])
            result = await drush.run(*cmd)
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def interface_translation_delete(
        source: str,
        langcode: str,
        context: str = "",
    ) -> dict[str, Any]:
        """Delete interface translation."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["locale:translate:delete", source, langcode]
            if context:
                cmd.extend(["--context", context])
            result = await drush.run(*cmd)
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def config_translation_list(
        page_limit: int = 50,
    ) -> dict[str, Any]:
        """List config translation entries."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": "50"}
            result = await jsonapi.get_resource("config_translation", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def config_translation_add(
        config_name: str,
        langcode: str,
        translation: dict[str, Any],
    ) -> dict[str, Any]:
        """Add config translation."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            import json
            translation_json = json.dumps(translation)
            result = await drush.run("config:translation:add", [config_name, langcode, translation_json])
            return _ensure_dict({"result": result})
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
