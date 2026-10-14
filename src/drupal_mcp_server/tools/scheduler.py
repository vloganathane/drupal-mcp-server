"""Scheduler/Queue management tools for Drupal."""

import re
from typing import Any

from fastmcp import FastMCP

from ._utils import b64_text as _b64
from ._utils import ensure_dict as _ensure_dict

# Drupal's own queue names are not bare identifiers: core ships names such as
# `node_grants:node_access` and `migrate.field_discovery`, so a check for
# [a-z_] would refuse queues that genuinely exist. Names travel into PHP as
# base64, so this only guards against nonsense rather than doing the escaping.
_QUEUE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:\-]*$")
_ITEM_ID = re.compile(r"^[0-9]+$")

# What QueueFactory can actually be told to build. Resolved in settings.php
# (`queue_service_<name>`, else `queue_default`, else the `queue.database`
# service) - never as an argument to anything, which is why `class_name` cannot
# be honoured when a queue is created.
_DEFAULT_QUEUE_CLASSES = frozenset({
    "Drupal\\Core\\Queue\\DatabaseQueue",
    "DatabaseQueue",
    "queue.database",
})

_CREATE_NOTE = (
    "Drupal has no queue registry: every name resolves to a DatabaseQueue over "
    "the shared queue table, and rows only appear when the first item is "
    "added. createQueue() was called and the queue is ready to accept items."
)


def _check_queue_name(queue_name: str) -> dict[str, Any] | None:
    """Return an error payload when the queue name cannot be used, else None."""
    if not _QUEUE_NAME.match(queue_name):
        return {"error": f"Invalid queue name: {queue_name!r}"}
    return None


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
        """List the jobs Drupal runs on cron, and when cron last ran.

        In Drupal 8+ a "cron job" is a module implementing `hook_cron`; there is
        no job registry and no `drupal_get_cron_jobs()` - that Drupal 7 function
        is what this tool used to call, so it returned "Call to undefined
        function" on every site it has ever run against.

        The implementations sit behind `ModuleHandler::invokeAllWith()`, whose
        callback is handed the listener without being forced to invoke it. Only
        `$module` is relied on: through Drupal 8-10 the callback receives
        `($function, $module, $arguments)` and in Drupal 11 `($listener,
        $module)`, so the module is the second argument in every version, and
        never calling the first argument is what stops listing a job from
        running cron.
        """
        if not drush:
            return {"error": "Drush not available"}
        try:
            php = (
                "$modules = []; "
                "\\Drupal::moduleHandler()->invokeAllWith('cron', "
                "function ($implementation, $module) use (&$modules) "
                "{ $modules[] = $module; }); "
                "sort($modules); "
                "$last = \\Drupal::state()->get('system.cron_last'); "
                "$cfg = \\Drupal::config('system.cron')->getRawData(); "
                "print json_encode(["
                "'modules' => $modules, "
                "'count' => count($modules), "
                "'last_run' => $last ? (int) $last : NULL, "
                "'last_run_iso' => $last ? date('c', (int) $last) : NULL, "
                "'logging' => $cfg['logging'] ?? NULL, "
                "'threshold' => $cfg['threshold'] ?? NULL"
                "]);"
            )
            result = await drush.run("ev", [php])
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
        bad = _check_queue_name(queue_name)
        if bad:
            return bad
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
        """Delete queue items: one by id, the oldest `count`, or the whole queue.

        Drush's `queue:delete` takes exactly one argument - the queue name - so
        the `item_id` and `count` forms cannot go through it: they passed extra
        arguments that Drush refused with "Too many arguments", and all three
        branches failed, so this tool never once succeeded.

        Even the plain case now runs in PHP rather than through Drush, because
        `queue:delete` only resolves queues that are registered as services and
        answers "Queue not found" for anything else - including a queue this
        very server just created with `queue_create`. `Queue::deleteQueue()` is
        what Drush calls internally, so the result is the same operation without
        Drush's registration requirement.

        `item_id` deliberately repeats the queue name in its condition even
        though core's own `DatabaseQueue::deleteItem()` does not - that method
        deletes by `item_id` alone, so without the name a request for an item in
        one queue would happily delete a different queue's item that happened to
        share the id.
        """
        if not drush:
            return {"error": "Drush not available"}
        bad = _check_queue_name(queue_name)
        if bad:
            return bad
        try:
            if item_id is not None and not _ITEM_ID.match(str(item_id)):
                return {"error": f"item_id must be a non-negative integer, got {item_id!r}"}
            if count is not None and (not isinstance(count, int) or count < 0):
                return {"error": f"count must be a non-negative integer, got {count!r}"}

            if item_id is not None:
                ident = int(str(item_id))
                # Drupal 11 stores every queue in one `queue` table with the
                # name in a column; older Drupal used one table per queue.
                # Whichever applies, `name` ends up in the condition so an item
                # belonging to another queue is never touched.
                php = (
                    "$name = base64_decode('" + _b64(queue_name) + "'); "
                    "$id = " + str(ident) + "; "
                    "$schema = \\Drupal::database()->schema(); "
                    "if ($schema->tableExists('queue')) { "
                    "  $deleted = (int) \\Drupal::database()->delete('queue')"
                    "->condition('item_id', $id)->condition('name', $name)->execute(); "
                    "} elseif (preg_match('/^[A-Za-z0-9_]+$/', $name) "
                    "&& $schema->tableExists('queue_' . $name)) { "
                    "  $deleted = (int) \\Drupal::database()->delete('queue_' . $name)"
                    "->condition('item_id', $id)->execute(); "
                    "} else { $deleted = 0; } "
                    "print json_encode(['queue' => $name, 'item_id' => $id, "
                    "'deleted' => $deleted, "
                    "'items_remaining' => (int) \\Drupal::queue($name)->numberOfItems()]);"
                )
                return _ensure_dict(await drush.run("ev", [php]))

            if count is not None:
                php = (
                    "$name = base64_decode('" + _b64(queue_name) + "'); "
                    "$wanted = " + str(int(count)) + "; "
                    "$queue = \\Drupal::queue($name); "
                    "$before = (int) $queue->numberOfItems(); "
                    "$deleted = 0; "
                    "while ($deleted < $wanted) { "
                    "  $item = $queue->claimItem(0); "
                    "  if (!$item) { break; } "
                    "  $queue->deleteItem($item); "
                    "  $deleted++; "
                    "} "
                    "print json_encode(['queue' => $name, 'requested' => $wanted, "
                    "'deleted' => $deleted, 'before' => $before, "
                    "'items_remaining' => (int) $queue->numberOfItems()]);"
                )
                return _ensure_dict(await drush.run("ev", [php]))

            php = (
                "$name = base64_decode('" + _b64(queue_name) + "'); "
                "$queue = \\Drupal::queue($name); "
                "$before = (int) $queue->numberOfItems(); "
                "$queue->deleteQueue(); "
                "$after = (int) $queue->numberOfItems(); "
                "print json_encode(['queue' => $name, 'deleted' => $before - $after, "
                "'before' => $before, 'items_remaining' => $after]);"
            )
            return _ensure_dict(await drush.run("ev", [php]))
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def queue_info(queue_name: str) -> dict[str, Any]:
        """Get queue information."""
        if not drush:
            return {"error": "Drush not available"}
        bad = _check_queue_name(queue_name)
        if bad:
            return bad
        try:
            # There is no `queue:info`; `queue:list` carries the same data.
            result = await drush.run("queue:list", ["--format=json"])
            if result.get("returncode") != 0:
                return _ensure_dict(result)
            # `queue:list --format=json` emits a list of rows; older Drush
            # emitted a name-keyed object. Accept either rather than assuming.
            data = result.get("data")
            if isinstance(data, dict):
                queues: dict[str, Any] = data
            elif isinstance(data, list):
                queues = {
                    row["queue"]: row
                    for row in data
                    if isinstance(row, dict) and "queue" in row
                }
            else:
                queues = {}
            detail = queues.get(queue_name)
            if detail is None:
                known = ", ".join(sorted(queues))[:400]
                return _ensure_dict({
                    "queue": queue_name,
                    "error": (
                        f"No queue named {queue_name!r}. Known queues: {known}"
                        if known
                        else f"No queue named {queue_name!r}, and this site "
                        "currently defines no queues at all (drush queue:list "
                        "returned none). Queues appear here once something "
                        "registers one with items."
                    ),
                })
            return _ensure_dict({"queue": queue_name, "info": detail})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def queue_create(queue_name: str, class_name: str = "Drupal\\Core\\Queue\\DatabaseQueue") -> dict[str, Any]:
        """Create a queue and make it ready to accept items.

        `class_name` is refused rather than silently dropped. Drupal resolves a
        queue's implementation in settings.php - `queue_service_<name>`, else
        `queue_default`, else the `queue.database` service - and that service
        must already exist in the container, so no API accepts a class name when
        a queue is created. Accepting it would let a caller believe they had a
        custom queue implementation when they had the default one.
        """
        if not drush:
            return {"error": "Drush not available"}
        bad = _check_queue_name(queue_name)
        if bad:
            return bad
        if class_name not in _DEFAULT_QUEUE_CLASSES:
            return {
                "error": (
                    f"class_name {class_name!r} cannot be honoured. Drupal picks "
                    "a queue implementation from the settings.php keys "
                    "`queue_service_<queue>` or `queue_default`, each pointing at "
                    "a service that must already be registered; there is no call "
                    "that takes a class name. Pass the default, or register the "
                    "service and set `queue_default` in settings.php."
                )
            }
        try:
            php = (
                "$name = base64_decode('" + _b64(queue_name) + "'); "
                "$queue = \\Drupal::queue($name); "
                "$queue->createQueue(); "
                "print json_encode(['queue' => $name, "
                "'class' => get_class($queue), "
                "'items' => (int) $queue->numberOfItems(), "
                "'ready' => TRUE]);"
            )
            result = await drush.run("ev", [php])
            payload = _ensure_dict(result)
            if "error" not in payload:
                payload["note"] = _CREATE_NOTE
            return payload
        except Exception as e:
            return {"error": str(e)}
