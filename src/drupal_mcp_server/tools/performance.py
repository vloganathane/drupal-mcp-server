"""Performance/APM tools for Drupal.

Drush has no ``exec`` command (verified against drush-ops/drush 13.x):
``php:eval`` is the command that evaluates code, and it receives arguments
directly -- no shell -- so the shell-era ``\\$`` escapes these tools used to
build would reach PHP as literal backslashes and fail to parse.
"""

from typing import Any

from fastmcp import FastMCP

from ._utils import drush_result as _drush_result
from ._utils import ensure_dict as _ensure_dict
from ._utils import php_single_quote as _php_quote


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")
    _jsonapi = deps.get("jsonapi_client")

    @mcp.tool()
    async def performance_query_log(
        limit: int = 100,
        min_duration: float = 0.0,
    ) -> dict[str, Any]:
        """Get the recent db_query watchdog entries (requires devel logging).

        ``min_duration`` is refused rather than ignored: watchdog rows carry
        no query duration, so a duration filter cannot be honored here --
        durations come from devel's own query log.
        """
        if not drush:
            return {"error": "Drush not available"}
        try:
            # Validate limit to prevent injection
            if not isinstance(limit, int) or limit < 1 or limit > 10000:
                return {"error": "limit must be an integer between 1 and 10000"}
            if min_duration:
                return {
                    "error": (
                        "watchdog records no query duration, so min_duration "
                        "cannot be applied; the entries returned are type "
                        "db_query (devel logging) with severity <= 4. Use "
                        "devel's query log for duration filtering."
                    )
                }
            code = (
                "$db = \\Drupal::database(); "
                "$query = $db->select('watchdog', 'w')"
                "  ->fields('w', ['message', 'timestamp', 'severity'])"
                "  ->condition('type', 'db_query')"
                "  ->condition('severity', 4, '<=')"
                f"  ->range(0, {limit})"
                "  ->orderBy('timestamp', 'DESC');"
                "print_r(json_encode($query->execute()->fetchAll()));"
            )
            result = await drush.run("php:eval", [code])
            return _drush_result(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def performance_cache_stats(
    ) -> dict[str, Any]:
        """Get cache performance statistics."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            code = (
                "$cache_bins = \\Drupal::service('cache_tags_invalidator')->getCacheBins(); "
                "$stats = []; "
                "foreach ($cache_bins as $bin) { "
                "  $stats[$bin] = \\Drupal::cache($bin)->getStats(); "
                "} "
                "print_r(json_encode($stats));"
            )
            result = await drush.run("php:eval", [code])
            return _drush_result(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def performance_redis_info(
    ) -> dict[str, Any]:
        """Get Redis server info."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            code = (
                "$redis = \\Drupal::service('redis.factory')->get('default'); "
                "$info = $redis->info(); "
                "print_r(json_encode($info));"
            )
            result = await drush.run("php:eval", [code])
            return _drush_result(result)
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
            code = (
                "$memcached = \\Drupal::service('memcached.factory')->get('default'); "
                "$stats = $memcached->getStats(); "
                "print_r(json_encode($stats));"
            )
            result = await drush.run("php:eval", [code])
            return _drush_result(result)
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
            code = (
                "$times = []; "
                f"for ($i = 0; $i < {runs}; $i++) {{ "
                "  $start = microtime(true); "
                f"  $response = \\Drupal::httpClient()->get({_php_quote(url)}); "
                "  $times[] = microtime(true) - $start; "
                "} "
                "$avg = array_sum($times) / count($times); "
                "$min = min($times); "
                "$max = max($times); "
                "print_r(json_encode(['avg' => $avg, 'min' => $min, 'max' => $max, 'runs' => $times]));"
            )
            result = await drush.run("php:eval", [code])
            return _drush_result(result)
        except Exception as e:
            return {"error": str(e)}
