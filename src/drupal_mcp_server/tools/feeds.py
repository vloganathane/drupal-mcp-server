"""Feeds/Import tools for Drupal."""

from typing import Any

from fastmcp import FastMCP

from ._utils import absent_entity as _absent_entity
from ._utils import ensure_dict as _ensure_dict


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")
    jsonapi = deps.get("jsonapi_client")

    @mcp.tool()
    async def feeds_feed_list(
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List all feeds."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
            result = await jsonapi.get_resource("feeds_feed", params)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def feeds_feed_get(
        feed_id: str,
        include: str = "",
    ) -> dict[str, Any]:
        """Get a single feed by ID."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            params = {}
            if include:
                params["include"] = include
            result = await jsonapi.get_by_id("feeds_feed", feed_id, params=params if params else None)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def feeds_feed_create(
        id: str,
        label: str,
        fetcher: str = "http",
        parser: str = "csv",
        processor: str = "entity:node",
        configuration: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new feed."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            feed_data: dict[str, Any] = {
                "type": "feeds_feed",
                "id": id,
                "label": label,
                "fetcher": fetcher,
                "parser": parser,
                "processor": processor,
            }
            if configuration:
                feed_data["configuration"] = configuration
            
            result = await jsonapi.create_resource("feeds_feed", feed_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def feeds_feed_update(
        feed_id: str,
        label: str | None = None,
        configuration: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update a feed."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            current = await jsonapi.get_by_id("feeds_feed", feed_id)
            current = _ensure_dict(current)
            if current.get("error"):
                return current
            
            update_data: dict[str, Any] = {"id": feed_id, "type": "feeds_feed"}
            if label is not None:
                update_data["label"] = label
            if configuration is not None:
                update_data["configuration"] = configuration
            
            result = await jsonapi.update_resource("feeds_feed", feed_id, update_data)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def feeds_feed_delete(
        feed_id: str,
    ) -> dict[str, Any]:
        """Delete a feed."""
        if not jsonapi:
            return {"error": "JSON:API not available"}
        try:
            result = await jsonapi.delete_resource("feeds_feed", feed_id)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def feeds_import(
        feed_id: str,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Run a feed import."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["feeds:import", feed_id]
            if source:
                cmd.extend(["--source", source])
            result = await drush.run(*cmd)
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def feeds_import_status(
        feed_id: str,
    ) -> dict[str, Any]:
        """Get feed import status."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["feeds:import-status", feed_id]
            result = await drush.run(*cmd)
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def feeds_log_list(
        feed_id: str | None = None,
        page_limit: int = 50,
        page_offset: int = 0,
    ) -> dict[str, Any]:
        """List feed import logs.

        Superseded by `feeds_import_status`, which reports the outcome of the
        current import. Feeds 3.x removed the log entity, so there is nothing
        of this shape to list on any site.
        """
        return _absent_entity(
            "feeds_log",
            "Feeds 3.x removed the log entity; an import's outcome is reported "
            "on the feed itself. Use feeds_import_status.",
        )

    @mcp.tool()
    async def feeds_tamper_list(
        feed_id: str,
    ) -> dict[str, Any]:
        """List tamper plugins for a feed."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["feeds:tamper:list", feed_id]
            result = await drush.run(*cmd)
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def feeds_parser_list(
    ) -> dict[str, Any]:
        """List available feed parsers."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["exec", [
                "\\$parsers = \\Drupal::service('plugin.manager.feeds.parser')->getDefinitions(); "
                "print_r(json_encode(array_keys(\\$parsers)));"
            ]]
            result = await drush.run(*cmd)
            return _ensure_dict({"parsers": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def feeds_fetcher_list(
    ) -> dict[str, Any]:
        """List available feed fetchers."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["exec", [
                "\\$fetchers = \\Drupal::service('plugin.manager.feeds.fetcher')->getDefinitions(); "
                "print_r(json_encode(array_keys(\\$fetchers)));"
            ]]
            result = await drush.run(*cmd)
            return _ensure_dict({"fetchers": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def feeds_processor_list(
    ) -> dict[str, Any]:
        """List available feed processors."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["exec", [
                "\\$processors = \\Drupal::service('plugin.manager.feeds.processor')->getDefinitions(); "
                "print_r(json_encode(array_keys(\\$processors)));"
            ]]
            result = await drush.run(*cmd)
            return _ensure_dict({"processors": result})
        except Exception as e:
            return {"error": str(e)}
