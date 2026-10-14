"""Scheduler/Queue management tools for Drupal."""

from typing import Any

from fastmcp import FastMCP

from ._utils import ensure_dict as _ensure_dict


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")

    @mcp.tool()
    async def cron_run() -> dict[str, Any]:
        """Run cron."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("cron")
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def cron_list() -> dict[str, Any]:
        """List scheduled cron jobs (via drush ev to get cron config)."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("ev", ["$jobs = &drupal_get_cron_jobs(); print_r($jobs);"])
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def queue_list() -> dict[str, Any]:
        """List all queues."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("queue:list", ["--format=json"])
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def queue_run(queue_name: str, limit: int = 100) -> dict[str, Any]:
        """Run a specific queue."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            # Drush 13 offers neither --limit nor --count on queue:run; it
            # always drains the whole queue. Claiming a limit we cannot honour
            # would be worse than saying so.
            result = await drush.run("queue:run", [queue_name])
            payload = _ensure_dict(result)
            if result.get("returncode") == 0:
                payload["requested_limit"] = limit
                payload["note"] = (
                    "Drush drains the whole queue and offers no per-run limit, "
                    f"so {limit!r} was not applied."
                )
            return payload
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def queue_delete(queue_name: str, item_id: str | None = None, count: int | None = None) -> dict[str, Any]:
        """Delete queue items."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            if item_id:
                result = await drush.run("queue:delete", [queue_name, item_id])
            elif count:
                result = await drush.run("queue:delete", [queue_name, f"--count={count}"])
            else:
                result = await drush.run("queue:delete", [queue_name, "--all"])
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def queue_info(queue_name: str) -> dict[str, Any]:
        """Get queue information."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            # There is no `queue:info`; `queue:list` carries the same data.
            result = await drush.run("queue:list")
            if result.get("returncode") != 0:
                return _ensure_dict(result)
            queues = result.get("data") or {}
            detail = queues.get(queue_name) if isinstance(queues, dict) else None
            if detail is None:
                return _ensure_dict({
                    "queue": queue_name,
                    "error": (
                        f"No queue named {queue_name!r}. Known queues: "
                        + ", ".join(sorted(queues))[:400]
                    ),
                })
            return _ensure_dict({"queue": queue_name, "info": detail})
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def queue_create(queue_name: str, class_name: str = "Drupal\\Core\\Queue\\DatabaseQueue") -> dict[str, Any]:
        """Create a new queue."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            # Validate queue_name to prevent injection
            import re
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', queue_name):
                return {"error": f"Invalid queue name: {queue_name}"}
            result = await drush.run("ev", [f"\\$queue = \\Drupal::queue()->create('{queue_name}'); print_r(\\$queue);"])
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}
