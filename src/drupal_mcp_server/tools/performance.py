"""Performance/APM tools for Drupal."""

from typing import Any

from fastmcp import FastMCP

from ._utils import ensure_dict as _ensure_dict


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")
    jsonapi = deps.get("jsonapi_client")

    @mcp.tool()
    async def performance_query_log(
        limit: int = 100,
        min_duration: float = 0.0,
    ) -> dict[str, Any]:
        """Get slow query log."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            # Validate limit to prevent injection
            if not isinstance(limit, int) or limit < 1 or limit > 10000:
                return {"error": "limit must be an integer between 1 and 10000"}
            cmd = ["exec", [
                "\\$db = \\Drupal::database(); "
                "\\$query = \\$db->select('watchdog', 'w')"
                "  ->fields('w', ['message', 'timestamp', 'severity'])"
                "  ->condition('type', 'db_query')"
                "  ->condition('severity', 4, '<=')"
                f"  ->range(0, {limit})"
                "  ->orderBy('timestamp', 'DESC');"
                "print_r(json_encode(\\$query->execute()->fetchAll()));"
            ]]
            result = await drush.run(*cmd)
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def performance_cache_stats(
    ) -> dict[str, Any]:
        """Get cache performance statistics."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["exec", [
                "\\$cache_bins = \\Drupal::service('cache_tags_invalidator')->getCacheBins(); "
                "\\$stats = []; "
                "foreach (\\$cache_bins as \\$bin) { "
                "  \\$stats[\\$bin] = \\Drupal::cache(\\$bin)->getStats(); "
                "} "
                "print_r(json_encode(\\$stats));"
            ]]
            result = await drush.run(*cmd)
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def performance_redis_info(
    ) -> dict[str, Any]:
        """Get Redis server info."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["exec", [
                "\\$redis = \\Drupal::service('redis.factory')->get('default'); "
                "\\$info = \\$redis->info(); "
                "print_r(json_encode(\\$info));"
            ]]
            result = await drush.run(*cmd)
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def performance_bigpipe_status(
    ) -> dict[str, Any]:
        """Check BigPipe status and configuration."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["config:get", "bigpipe.settings"]
            result = await drush.run(*cmd)
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def performance_bigpipe_enable(
        enable: bool = True,
    ) -> dict[str, Any]:
        """Enable or disable BigPipe."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["config:set", "bigpipe.settings", "enabled", str(enable).lower()]
            result = await drush.run(*cmd)
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def performance_memcached_stats(
    ) -> dict[str, Any]:
        """Get Memcached statistics."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            cmd = ["exec", [
                "\\$memcached = \\Drupal::service('memcached.factory')->get('default'); "
                "\\$stats = \\$memcached->getStats(); "
                "print_r(json_encode(\\$stats));"
            ]]
            result = await drush.run(*cmd)
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def performance_page_load_analyze(
        url: str,
        runs: int = 3,
    ) -> dict[str, Any]:
        """Analyze page load performance."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            # Validate URL and runs to prevent injection
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if parsed.scheme not in ('http', 'https') or not parsed.netloc:
                return {"error": f"Invalid URL: {url}"}
            if not isinstance(runs, int) or runs < 1 or runs > 100:
                return {"error": "runs must be an integer between 1 and 100"}
            cmd = ["exec", [
                "\\$times = []; "
                f"for (\\$i = 0; \\$i < {runs}; \\$i++) {{ "
                "  \\$start = microtime(true); "
                f"  \\$response = \\Drupal::httpClient()->get('{url}'); "
                "  \\$times[] = microtime(true) - \\$start; "
                "} "
                "\\$avg = array_sum(\\$times) / count(\\$times); "
                "\\$min = min(\\$times); "
                "\\$max = max(\\$times); "
                "print_r(json_encode(['avg' => \\$avg, 'min' => \\$min, 'max' => \\$max, 'runs' => \\$times]));"
            ]]
            result = await drush.run(*cmd)
            return _ensure_dict({"result": result})
        except Exception as e:
            return {"error": str(e)}
