#!/usr/bin/env python3
"""Live verification of the layout_builder_* tools.

These six tools could never work before - they asked JSON:API for a resource
that has never existed. They now go through Drush to the real Layout Builder
API, which needs a running site with layout_builder enabled and the view
display marked overridable, so this is checked against the site rather than
mocked.

    python tests/live/layout_builder_test.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from bootstrap import live_nid
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parents[2]
PROJECT = HERE / "drupal-live"
VENV = HERE / "venv"
BASE = os.environ.get("DRUPAL_BASE_URL", "https://drupal-live.ddev.site")


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


def check(label: str, payload: dict, ok: bool, note: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label:44} {note[:70]}")
    return ok


async def main() -> int:
    # The sweep deletes what it touches, so a hardcoded node id made this suite
    # fail depending on what ran before it: the tool answered correctly with
    # "No node with id 3" and the fixture was the thing that was wrong.
    nid = live_nid()

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

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            print(f"{len(tools)} tools registered\n")

            # 1. read --------------------------------------------------------
            got = await call(session, "layout_builder_get",
                             {"entity_type": "node", "bundle": "article"})
            start_len = len(got.get("sections") or [])
            ok = "error" not in got and got.get("enabled") is True
            passed += check("layout_builder_get", got, ok,
                            f"enabled={got.get('enabled')} sections={start_len}")
            failed += 0 if ok else 1

            # 2. sections list ------------------------------------------------
            secs = await call(session, "layout_builder_sections_list",
                              {"entity_type": "node", "bundle": "article"})
            ok = "error" not in secs and isinstance(secs.get("sections"), list)
            passed += check("layout_builder_sections_list", secs, ok,
                            f"{len(secs.get('sections') or [])} sections")
            failed += 0 if ok else 1

            # 3. add a section ------------------------------------------------
            added = await call(session, "layout_builder_section_add", {
                "entity_type": "node", "bundle": "article",
                "section": {
                    "layout_id": "layout_onecol",
                    "components": [
                        {"plugin": "system_branding_block", "region": "content"},
                        "system_main_block",
                    ],
                },
            })
            after_add = len(added.get("sections") or [])
            ok = "error" not in added and after_add == start_len + 1
            passed += check("layout_builder_section_add", added, ok,
                            f"{start_len} -> {after_add}")
            failed += 0 if ok else 1

            # 4. replace the whole layout --------------------------------------
            replaced = await call(session, "layout_builder_create", {
                "entity_type": "node", "bundle": "article",
                "layout": {"sections": [
                    {"layout_id": "layout_onecol",
                     "components": ["page_title_block"]},
                    {"layout_id": "layout_onecol",
                     "components": ["system_main_block"]},
                ]},
            })
            ok = ("error" not in replaced
                  and len(replaced.get("sections") or []) == 2
                  and replaced.get("sections_written") == 2)
            passed += check("layout_builder_create", replaced, ok,
                            f"sections={len(replaced.get('sections') or [])}")
            failed += 0 if ok else 1

            # 5. update without a layout reports state --------------------------
            reported = await call(session, "layout_builder_update",
                                  {"entity_type": "node", "bundle": "article"})
            ok = "error" not in reported and reported.get("section_count") == 2
            passed += check("layout_builder_update (report)", reported, ok,
                            f"count={reported.get('section_count')}")
            failed += 0 if ok else 1

            # 6. an unknown bundle must explain, not 404 ------------------------
            missing = await call(session, "layout_builder_get",
                                 {"entity_type": "node", "bundle": "nosuchtype"})
            ok = "error" in missing and "entity view display" in str(missing["error"])
            passed += check("layout_builder_get (missing display)", missing, ok,
                            str(missing.get("error"))[:60])
            failed += 0 if ok else 1

            # 7. overrides: list ------------------------------------------------
            listed = await call(session, "layout_builder_override_remove",
                                {"entity_type": "node", "bundle": "article"})
            ok = "error" not in listed and isinstance(listed.get("overridden"), list)
            passed += check("override_remove (list mode)", listed, ok,
                            f"overridden={listed.get('overridden')}")
            failed += 0 if ok else 1

            # 9. real round trip: create an override, then revert it -------------
            #    drush_php_eval is used for the setup because it was one of the
            #    tools broken by the shlex-splitting bug - this proves it too.
            create_php = (
                "$n = \\Drupal\\node\\Entity\\Node::load(" + str(nid) + ");"
                "$d = \\Drupal::entityTypeManager()->getStorage('entity_view_display')"
                "->load('node.article.default');"
                "$ov = $d->getOverridesSectionStorageForEntity($n);"
                "$s = new \\Drupal\\layout_builder\\Section('layout_onecol');"
                "$c = new \\Drupal\\layout_builder\\SectionComponent("
                "\\Drupal::service('uuid')->generate(), $s->getDefaultRegion(), "
                "['id' => 'system_main_block']);"
                "$s->appendComponent($c);"
                "$ov->appendSection($s);"
                "$ov->save();"
                "print json_encode(['created' => TRUE]);"
            )
            made = await call(session, "drush_php_eval", {"code": create_php})
            created = "error" not in made
            passed += check("drush_php_eval creates an override", made, created,
                            str(made)[:60])
            failed += 0 if created else 1

            listed2 = await call(session, "layout_builder_override_remove",
                                {"entity_type": "node", "bundle": "article"})
            now_listed = listed2.get("overridden") or []
            saw_it = str(nid) in [str(x) for x in now_listed]
            passed += check("override_remove sees the override", listed2, saw_it,
                            f"overridden={now_listed}")
            failed += 0 if saw_it else 1

            undone = await call(session, "layout_builder_override_remove",
                                {"entity_type": "node", "bundle": "article",
                                 "entity_id": str(nid)})
            real = undone.get("reverted") is True
            passed += check("override_remove reverts it", undone, real,
                            f"reverted={undone.get('reverted')} "
                            f"removed={undone.get('sections_removed')}")
            failed += 0 if real else 1

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
