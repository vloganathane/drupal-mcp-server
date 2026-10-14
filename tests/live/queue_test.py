#!/usr/bin/env python3
"""Live verification of the scheduler tools.

Three of these six tools were dead in ways only a real Drupal shows:

  * ``cron_list`` asked for Drupal 7's ``drupal_get_cron_jobs()``, removed in
    Drupal 8, so it answered "Call to undefined function" on every site it has
    ever run against.
  * ``queue_create`` put a shell escape into PHP that never passes through a
    shell, so PHP saw a literal backslash and died with a ParseError first.
  * ``queue_delete`` handed Drush a second argument on all three paths while
    ``queue:delete`` accepts exactly one, so "Too many arguments" was the
    answer every single time.

The interesting assertion here is that deleting by ``item_id`` stays inside the
queue it was asked about. Core's own ``DatabaseQueue::deleteItem()`` deletes by
id alone, so without a second queue to compare against the test would pass
whether or not the name condition was there.

    python tests/live/queue_test.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parents[2]
PROJECT = HERE / "drupal-live"
VENV = HERE / "venv"
BASE = os.environ.get("DRUPAL_BASE_URL", "https://drupal-live.ddev.site")

QUEUE = "live_queue_test"
OTHER = "live_queue_other"


async def call(session: ClientSession, tool: str, args: dict) -> dict:
    res = await session.call_tool(tool, args, read_timeout_seconds=180)
    text = "".join(getattr(c, "text", "") for c in res.content)
    try:
        payload = json.loads(text)
    except Exception:
        payload = {"error": text[:400]}
    if isinstance(payload, dict):
        return payload
    return {"value": payload}


def data_of(payload: dict) -> Any:
    """The tool's own result, past Drush's {returncode, data} envelope."""
    data = payload.get("data")
    if isinstance(data, str):
        try:
            return json.loads(data)
        except Exception:
            return data
    return data


async def eval_php(session: ClientSession, php: str) -> Any:
    """Run PHP through the `drush_php_eval` tool and return parsed stdout."""
    got = await call(session, "drush_php_eval", {"code": php})
    if got.get("error") or got.get("returncode"):
        return got
    return data_of(got)


async def queue_ids(session: ClientSession, name: str) -> list[int]:
    """Item ids currently held by `name`, oldest first."""
    php = (
        "print json_encode(array_map(fn($r) => (int) $r->item_id, "
        "\\Drupal::database()->query("
        "'SELECT item_id FROM queue WHERE name = :n ORDER BY item_id', "
        "[':n' => '" + name + "'])->fetchAll()));"
    )
    ids = await eval_php(session, php)
    return ids if isinstance(ids, list) else []


def check(label: str, payload: dict, ok: bool, note: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label:46} {note[:70]}")
    return ok


async def main() -> int:
    env = dict(os.environ)
    env.update({
        "DRUPAL_BASE_URL": BASE,
        "DRUPAL_USERNAME": "admin",
        "DRUPAL_PASSWORD": "admin",
        "DRUPAL_VERIFY_SSL": "false",
        "MCP_LOG_LEVEL": "ERROR",
        "DRUSH_PATH": "ddev drush",
    })
    params = StdioServerParameters(
        command="sh",
        args=["-c", f"cd {PROJECT} && exec {VENV}/bin/drupal-mcp"],
        env=env,
    )

    passed = failed = 0

    def record(label: str, payload: dict, ok: bool, note: str = "") -> None:
        """Tally and report one assertion."""
        nonlocal passed, failed
        if ok:
            passed += 1
        else:
            failed += 1
        check(label, payload, ok, note)

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            print(f"{len(tools)} tools registered\n")

            # --- cron_list -------------------------------------------------
            print("cron_list")

            before = await eval_php(
                session,
                "print (string) \\Drupal::state()->get('system.cron_last');",
            )
            got = await call(session, "cron_list", {})
            summary = data_of(got) or {}
            modules = summary.get("modules") if isinstance(summary, dict) else None
            after = await eval_php(
                session,
                "print (string) \\Drupal::state()->get('system.cron_last');",
            )

            ok = "error" not in got and isinstance(modules, list) and len(modules) >= 1
            record("lists hook_cron modules", got, ok,
                            f"{len(modules or [])} modules")
            ok = isinstance(modules, list) and "system" in modules
            record("includes core's system_cron", got, ok,
                            ",".join((modules or [])[:6]))
            # Listing a job must not execute it: `invokeAllWith` hands the
            # callback the implementation, so a careless callback would run cron.
            ok = before == after and "drupal_get_cron_jobs" not in json.dumps(got)
            record("does not run cron to list it", got, ok,
                            f"last_run {before} unchanged" if before == after
                            else f"cron_last moved {before} -> {after}")
            ok = isinstance(summary, dict) and summary.get("last_run") is not None
            record("reports when cron last ran", got, ok,
                            str((summary or {}).get("last_run_iso"))[:40])

            # --- queue_create ---------------------------------------------
            print("\nqueue_create")

            got = await call(session, "queue_create", {"queue_name": QUEUE})
            created = data_of(got) or {}
            ok = "error" not in got and created.get("ready") is True
            record("creates and resolves a queue", got, ok,
                            f"class={created.get('class')} items={created.get('items')}")
            ok = "no queue registry" in str(got.get("note", ""))
            record("says what was actually created", got, ok,
                            str(got.get("note", ""))[:60])

            got = await call(session, "queue_create",
                             {"queue_name": QUEUE, "class_name": "Acme\\FancyQueue"})
            ok = "cannot be honoured" in str(got.get("error", ""))
            record("refuses an unhonourable class_name", got, ok,
                            str(got.get("error", ""))[:70])

            got = await call(session, "queue_create", {"queue_name": "../../etc/passwd"})
            ok = "Invalid queue name" in str(got.get("error", ""))
            record("rejects a queue name that is not one", got, ok,
                            str(got.get("error", ""))[:50])

            # --- queue_list / queue_info -----------------------------------
            print("\nqueue_list / queue_info")

            got = await call(session, "queue_list", {})
            ok = "error" not in got and got.get("returncode") in (0, None)
            record("queue_list runs", got, ok,
                            str(data_of(got))[:50])

            got = await call(session, "queue_info", {"queue_name": "no_such_queue"})
            err = str(got.get("error", ""))
            ok = "No queue named 'no_such_queue'" in err
            record("queue_info names the unknown queue", got, ok,
                            err[:70])
            # `drush queue:list` reports registered queues only, so an ad-hoc
            # queue is legitimately absent - the message must not be a bare
            # "Known queues: " with nothing after it.
            ok = "Known queues: " not in err or err.split("Known queues: ", 1)[1][:1] != ""
            record("explains an empty queue list", got, ok,
                            "says the site defines none" if ok else err[:60])

            # --- seeding ----------------------------------------------------
            print("\nseeding")

            seed = await eval_php(session, (
                "$q = \\Drupal::queue('" + QUEUE + "'); $q->deleteQueue(); "
                "$q->createItem(['n' => 1]); $q->createItem(['n' => 2]); "
                "$q->createItem(['n' => 3]); "
                "$o = \\Drupal::queue('" + OTHER + "'); $o->deleteQueue(); "
                "$o->createItem(['n' => 9]); "
                "print json_encode(['main' => (int) $q->numberOfItems(), "
                "'other' => (int) $o->numberOfItems()]);"
            ))
            ok = isinstance(seed, dict) and seed.get("main") == 3 and seed.get("other") == 1
            record("seeded 3 items here and 1 elsewhere", {"seed": seed}, ok,
                            json.dumps(seed) if not ok else "3 + 1")

            ids = await queue_ids(session, QUEUE)
            other_ids = await queue_ids(session, OTHER)

            # --- queue_delete ----------------------------------------------
            print("\nqueue_delete")

            got = await call(session, "queue_delete", {"queue_name": QUEUE, "count": 1})
            got_data = data_of(got) or {}
            ok = "error" not in got and got_data.get("deleted") == 1
            record("count=1 removes exactly one", got, ok,
                            json.dumps(got_data)[:70])

            ids = await queue_ids(session, QUEUE)
            got = await call(session, "queue_delete",
                             {"queue_name": QUEUE, "item_id": str(ids[0])})
            got_data = data_of(got) or {}
            ok = "error" not in got and got_data.get("deleted") == 1
            record("item_id removes exactly that item", got, ok,
                            json.dumps(got_data)[:70])

            # The assertion that cannot be made without a second queue: ask for
            # an item id that belongs to OTHER while naming QUEUE. Core's
            # deleteItem() would remove it; the name condition must not.
            got = await call(session, "queue_delete",
                             {"queue_name": QUEUE, "item_id": str(other_ids[0])})
            got_data = data_of(got) or {}
            ok = "error" not in got and got_data.get("deleted") == 0
            record("leaves another queue's item alone", got, ok,
                            json.dumps(got_data)[:70])
            still = await queue_ids(session, OTHER)
            ok = len(still) == 1
            record("other queue still holds its item", {"ids": still}, ok,
                            f"{len(still)} item(s) remain")

            got = await call(session, "queue_delete", {"queue_name": QUEUE})
            got_data = data_of(got) or {}
            left = await queue_ids(session, QUEUE)
            ok = "error" not in got and len(left) == 0
            record("plain call empties the queue", got, ok,
                            f"returncode={got.get('returncode')} remaining={len(left)}")

            got = await call(session, "queue_delete", {"queue_name": QUEUE, "item_id": "abc"})
            ok = "item_id must be a non-negative integer" in str(got.get("error", ""))
            record("rejects a non-numeric item_id", got, ok,
                            str(got.get("error", ""))[:55])

            # --- cleanup ----------------------------------------------------
            await eval_php(session, (
                "\\Drupal::queue('" + QUEUE + "')->deleteQueue(); "
                "\\Drupal::queue('" + OTHER + "')->deleteQueue(); "
                "print 'cleaned';"
            ))

    print("\n" + "=" * 60)
    print(f"  passed: {passed}   failed: {failed}")
    print("=" * 60)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
