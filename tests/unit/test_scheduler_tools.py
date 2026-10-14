"""Regression tests for the scheduler tools.

Three of the six scheduler tools were dead in ways only a live site exposed:

- ``cron_list`` asked for Drupal 7's ``drupal_get_cron_jobs()``, which Drupal 8
  removed, so it answered "Call to undefined function" on every site it has ever
  run against.
- ``queue_create`` put a shell escape (``\\$``) into PHP that is never passed
  through a shell, so PHP saw a literal backslash and died with a ParseError.
- ``queue_delete`` appended a second argument on all three paths even though
  Drush's ``queue:delete`` accepts exactly one (``name``), so "Too many
  arguments" was the answer every single time.

Each test pins the specific shape that was wrong, so none can return silently.
"""

import asyncio
from typing import Any

from tests.unit.test_tool_utils import _Drush, _register


def _php(drush: _Drush, command: str = "ev") -> str:
    """Return the PHP handed to ``drush <command>``."""
    for cmd, args in drush.calls:
        if cmd == command and args:
            return args[0]
    raise AssertionError(f"expected a {command!r} call, saw {drush.calls!r}")


def _ok(data: Any) -> dict[str, Any]:
    return {"returncode": 0, "data": data}


# --- cron_list -----------------------------------------------------------


def test_cron_list_does_not_call_a_drupal_7_function():
    """`drupal_get_cron_jobs()` stopped existing in Drupal 8.

    The replacement enumerates `hook_cron` implementations through
    `ModuleHandler::invokeAllWith()`, which exists from Drupal 8 onwards.
    """
    drush = _Drush(_ok({"modules": ["system"], "count": 1, "last_run": None}))
    fns = _register("scheduler", drush_client=drush)

    result = asyncio.run(fns["cron_list"]())

    php = _php(drush)
    assert "drupal_get_cron_jobs" not in php
    assert "invokeAllWith('cron'" in php
    assert "error" not in result


def test_cron_list_enumerates_jobs_without_running_them():
    """`invokeAllWith` hands the callback the implementation itself.

    Calling that first argument would run every module's cron on what the user
    asked to be a read-only listing. Only `$module` may be used, and it is the
    second argument in both the Drupal 8-10 `($function, $module, $arguments)`
    and Drupal 11 `($listener, $module)` signatures.
    """
    drush = _Drush(_ok({"modules": ["system"], "count": 1}))
    fns = _register("scheduler", drush_client=drush)

    asyncio.run(fns["cron_list"]())

    php = _php(drush)
    assert "$implementation(" not in php
    assert "$modules[] = $module" in php


# --- queue_delete --------------------------------------------------------


def test_queue_delete_plain_reaches_every_queue():
    """`drush queue:delete` only resolves queues registered as a service.

    It answered "Queue not found" for a queue `queue_create` had just made, and
    for anything on a site with no queue workers registered at all. Going
    through `Queue::deleteQueue()` - the call Drush makes internally - works
    whether or not a service exists, and no command receives a second argument.
    """
    drush = _Drush(_ok({"deleted": 3, "before": 3, "items_remaining": 0}))
    fns = _register("scheduler", drush_client=drush)

    asyncio.run(fns["queue_delete"]("my_queue"))

    # The shape of the original failure: an extra argument on a command that
    # takes exactly one.
    assert all(len(args) == 1 for _, args in drush.calls), drush.calls
    php = _php(drush)
    assert "deleteQueue()" in php
    assert "queue:delete" not in [cmd for cmd, _ in drush.calls]


def test_queue_delete_item_id_never_sends_a_second_drush_argument():
    drush = _Drush(_ok({"deleted": 1}))
    fns = _register("scheduler", drush_client=drush)

    asyncio.run(fns["queue_delete"]("my_queue", item_id="7"))

    assert all(len(args) == 1 for _, args in drush.calls)
    php = _php(drush)
    assert "$id = 7" in php
    # Core's own `DatabaseQueue::deleteItem()` deletes by item_id alone, which
    # would happily hit another queue's item sharing that id. The queue name
    # must be in the condition alongside it.
    assert "condition('name', $name)" in php
    assert "condition('item_id', $id)" in php


def test_queue_delete_count_deletes_at_most_that_many():
    drush = _Drush(_ok({"deleted": 1}))
    fns = _register("scheduler", drush_client=drush)

    asyncio.run(fns["queue_delete"]("my_queue", count=3))

    php = _php(drush)
    assert "$wanted = 3" in php
    assert "claimItem(0)" in php
    assert all(cmd != "queue:delete" for cmd, _ in drush.calls)


def test_queue_php_carries_no_shell_escapes():
    """A `\\$` reaches PHP as a literal backslash, not as `$`.

    Arguments are argv and never go through a shell, so nothing strips the
    escape - which is precisely why queue_create's statement failed to parse on
    every call.
    """
    drush = _Drush(_ok({"deleted": 1}))
    fns = _register("scheduler", drush_client=drush)

    asyncio.run(fns["queue_delete"]("my_queue", item_id="1"))
    asyncio.run(fns["queue_create"]("my_queue"))

    for cmd, args in drush.calls:
        if cmd == "ev":
            assert "\\$" not in args[0], f"shell escape in {cmd} {args[0]!r}"


def test_queue_delete_rejects_a_non_numeric_item_id():
    drush = _Drush(_ok({}))
    fns = _register("scheduler", drush_client=drush)

    result = asyncio.run(fns["queue_delete"]("my_queue", item_id="1; DROP TABLE x"))

    assert "item_id" in result["error"]
    assert drush.calls == []


def test_queue_delete_rejects_a_queue_name_that_is_not_a_name():
    """Drupal's queue names allow `:`, `.` and `-` - core ships such names."""
    drush = _Drush(_ok({}))
    fns = _register("scheduler", drush_client=drush)

    good = asyncio.run(fns["queue_delete"]("node_grants:node_access", count=1))
    assert "error" not in good

    drush.calls.clear()
    bad = asyncio.run(fns["queue_delete"]("not a queue; rm -rf /"))
    assert "Invalid queue name" in bad["error"]
    assert drush.calls == []


# --- queue_create --------------------------------------------------------


def test_queue_create_refuses_a_class_it_cannot_install():
    """Drupal resolves queue implementations from settings.php, not from a call.

    Taking `class_name` at face value would let a caller believe they had a
    custom queue implementation while the factory built the default one
    regardless, so it is refused rather than quietly dropped.
    """
    drush = _Drush(_ok({}))
    fns = _register("scheduler", drush_client=drush)

    result = asyncio.run(fns["queue_create"]("my_queue", class_name="Acme\\FancyQueue"))

    assert "cannot be honoured" in result["error"]
    assert "settings.php" in result["error"]
    assert drush.calls == []


def test_queue_create_accepts_the_default_class():
    drush = _Drush(_ok({
        "queue": "my_queue",
        "class": "Drupal\\Core\\Queue\\DatabaseQueue",
        "items": 0,
        "ready": True,
    }))
    fns = _register("scheduler", drush_client=drush)

    result = asyncio.run(fns["queue_create"]("my_queue"))

    assert "error" not in result
    assert result["data"]["ready"] is True
    # Without a queue registry, "created" would overstate what happened.
    assert "no queue registry" in result["note"]


def test_queue_create_rejects_an_unusable_queue_name():
    drush = _Drush(_ok({}))
    fns = _register("scheduler", drush_client=drush)

    result = asyncio.run(fns["queue_create"]("../../etc/passwd"))

    assert "Invalid queue name" in result["error"]
    assert drush.calls == []


# --- queue_info ----------------------------------------------------------


def test_queue_info_reads_the_list_as_json():
    """`queue:list` defaults to a table, which cannot be parsed back.

    Its name is also looked up by the row key rather than assumed to be an
    object, because modern Drush emits a list of rows.
    """
    drush = _Drush(_ok([{"queue": "my_queue", "items": 4, "class": "x"}]))
    fns = _register("scheduler", drush_client=drush)

    result = asyncio.run(fns["queue_info"]("my_queue"))

    assert drush.calls == [("queue:list", ["--format=json"])]
    assert result["info"]["items"] == 4
