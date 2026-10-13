"""Metatag and SEO tools for Drupal."""

from typing import Any

from fastmcp import FastMCP

from ._utils import ensure_dict as _ensure_dict


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")
    jsonapi = deps.get("jsonapi_client")

    @mcp.tool()
    async def metatag_config_list(
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List all metatag configurations."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            result = await jsonapi.get_resource("metatag_config", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def metatag_config_get(
        config_id: str,
        include: str = "",
    ) -> dict[str, Any]:
        """Get a single metatag configuration by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("metatag_config", config_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def metatag_config_create(
        id: str,
        label: str,
        entity_type: str,
        bundle: str | None = None,
        tags: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new metatag configuration."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            config_data: dict[str, Any] = {
                "type": "metatag_config",
                "id": id,
                "label": label,
                "entity_type": entity_type,
            }
            if bundle:
                config_data["bundle"] = bundle
            if tags:
                config_data["tags"] = tags
            
            result = await jsonapi.create_resource("metatag_config", config_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def metatag_config_update(
        config_id: str,
        label: str | None = None,
        tags: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update a metatag configuration."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            current = await jsonapi.get_by_id("metatag_config", config_id)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data: dict[str, Any] = {"id": config_id, "type": "metatag_config"}
            if label is not None:
                update_data["label"] = label
            if tags is not None:
                update_data["tags"] = tags
            
            result = await jsonapi.update_resource("metatag_config", config_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def metatag_defaults_get(
        entity_type: str,
        bundle: str | None = None,
    ) -> dict[str, Any]:
        """Get default metatag values for entity type/bundle."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            entity = f"{entity_type}"
            if bundle:
                entity += f".{bundle}"
            result = await drush.run("config:get", [f"metatag.{entity}"])
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def metatag_defaults_set(
        entity_type: str,
        bundle: str | None = None,
        tags: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Set default metatag values for entity type/bundle."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            entity = f"{entity_type}"
            if bundle:
                entity += f".{bundle}"
            
            if tags is None:
                tags = {
                    "title": "[node:title] | [site:name]",
                    "description": "[node:summary]",
                    "canonical_url": "[node:url]",
                    "og_title": "[node:title] | [site:name]",
                    "og_description": "[node:summary]",
                    "og_image": "[node:field_image]",
                    "og_type": "article",
                    "twitter_cards_type": "summary_large_image",
                    "twitter_title": "[node:title] | [site:name]",
                    "twitter_description": "[node:summary]",
                    "twitter_image": "[node:field_image]",
                }
            
            import json
            tags_json = json.dumps(tags)
            result = await drush.run("config:set", [f"metatag.{entity}", tags_json])
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def metatag_token_list(
        entity_type: str | None = None,
    ) -> dict[str, Any]:
        """List available metatag tokens."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["token:list"]
            if entity_type:
                cmd.append(entity_type)
            result = await drush.run(*cmd)
            return _ensure_dict({"tokens": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def metatag_canonical_set(
        entity_type: str,
        entity_id: str,
        canonical_url: str,
    ) -> dict[str, Any]:
        """Set canonical URL for an entity."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            # Update entity with canonical URL
            resource = f"{entity_type}--{entity_type}"
            update_data = {
                "id": entity_id,
                "type": resource,
                "canonical_url": canonical_url,
            }
            result = await jsonapi.update_resource(resource, entity_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def metatag_jsonld_generate(
        entity_type: str,
        entity_id: str,
        schema_type: str = "Article",
    ) -> dict[str, Any]:
        """Generate JSON-LD structured data for entity."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            entity = await jsonapi.get_by_id(entity_type, entity_id)
            entity = _ensure_dict(entity)
            if entity.get("error"):
                return entity
            
            data = entity.get("data", {})
            attributes = data.get("attributes", {})
            
            jsonld = {
                "@context": "https://schema.org",
                "@type": schema_type,
                "headline": attributes.get("title", ""),
                "description": attributes.get("body", {}).get("summary", ""),
                "image": attributes.get("field_image", []),
                "datePublished": attributes.get("created", ""),
                "dateModified": attributes.get("changed", ""),
                "author": {
                    "@type": "Person",
                    "name": attributes.get("uid", {}).get("name", ""),
                },
                "publisher": {
                    "@type": "Organization",
                    "name": "[site:name]",
                },
            }
            
            return {"jsonld": jsonld}
        except Exception as e:
            return {"error": str(e)}
