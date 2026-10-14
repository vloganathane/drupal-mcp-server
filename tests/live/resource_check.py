#!/usr/bin/env python3
"""Check every JSON:API resource name our tools ask for against Drupal.

A tool that requests a resource Drupal has never heard of fails in a way that
looks environmental: a 404 that reads like "module not installed". `views_list`
did exactly this -- it asked for `views_view` while the entity type has been
`view` since Drupal 8, so all six views tools were dead on a site with Views
perfectly healthy, and the sweep recorded three of them as BLOCKED and three
as ordinary lookup misses.

This asks Drupal for the entity types it actually knows, then compares:

    OK          the resource is in the JSON:API index
    NOT_EXPOSED Drupal knows the type but JSON:API does not expose it
    WRONG       Drupal has no such entity type -- our tool is naming something
                that cannot exist, whatever modules are installed

WRONG is the interesting one and is always our bug. NOT_EXPOSED usually means
the module is installed but the entity type is hidden from JSON:API, which is
worth a look but is rarely a defect.

Everything is asked through our own MCP server, so running this also
exercises `drush_php_eval` and `jsonapi_resource_types`.

    python tests/live/resource_check.py
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parents[2]
PROJECT = HERE / "drupal-live"
VENV = HERE / "venv"
BASE = os.environ.get("DRUPAL_BASE_URL", "https://drupal-live.ddev.site")

# Every literal our code hands to a JSON:API call.
_CALL = re.compile(
    r"(get_resource|get_by_id|create_resource|update_resource|delete_resource)"
    r"\(\s*(?:resource_type\s*=\s*)?[\"']([A-Za-z0-9_.-]+)[\"']"
)

# Resource names that are not entity types and must not be judged as such.
# `jsonapi` is the index document itself, addressed by get_index().
NON_ENTITY = {"jsonapi"}


def tool_resources() -> dict[str, list[str]]:
    """Resource name -> the call sites that ask for it."""
    found: dict[str, list[str]] = {}
    for path in sorted((HERE / "src" / "drupal_mcp_server").rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            for match in _CALL.finditer(line):
                name = match.group(2)
                if "--" in name:
                    name = name.split("--", 1)[0]
                found.setdefault(name, []).append(f"{path.stem}:{lineno}")
    return found


async def call(session: ClientSession, tool: str, args: dict | None = None) -> dict:
    res = await session.call_tool(tool, args or {}, read_timeout_seconds=900)
    text = "".join(getattr(c, "text", "") for c in res.content)
    try:
        import json
        return json.loads(text)
    except Exception:
        return {"raw": text}


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

    # Every entity type Drupal knows, with the module that provides it.
    defs_code = (
        "$o = []; foreach (\\Drupal::entityTypeManager()->getDefinitions() as $id => $d) "
        "{ $o[$id] = $d->getProvider(); } print json_encode($o);"
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            known = (await call(session, "drush_php_eval", {"code": defs_code})).get("data") or {}
            if not isinstance(known, dict) or not known:
                print("could not read entity type definitions from Drupal", file=sys.stderr)
                return 2
            # The index returns `node--article`; the check is against the
            # entity type, so the bundle half is dropped.
            listed = (await call(session, "jsonapi_resource_types")).get("resource_types") or []
            exposed = {str(t).split("--", 1)[0] for t in listed}

    resources = tool_resources()
    wrong, hidden, ok = [], [], []
    for name in sorted(resources):
        if name in NON_ENTITY:
            ok.append(name)
        elif name in exposed:
            ok.append(name)
        elif name in known:
            hidden.append((name, known[name]))
        else:
            wrong.append((name, resources[name]))

    print(f"our tools ask for {len(resources)} distinct resource names")
    print(f"Drupal knows {len(known)} entity types; JSON:API exposes {len(exposed)}\n")

    if wrong:
        print(f"=== WRONG ({len(wrong)}) -- our bug, no module will fix these ===")
        for name, sites in wrong:
            print(f"  {name:26} {sites[0]:20} {len(sites)} call(s)")
            # Suggest the closest real name, which is usually the answer.
            close = [k for k in known if k.startswith(name.split("_")[0])]
            if close:
                print(f"    did you mean: {', '.join(sorted(close)[:4])}")
        print()

    if hidden:
        print(f"=== NOT EXPOSED ({len(hidden)}) -- installed, but JSON:API hides it ===")
        for name, provider in hidden:
            print(f"  {name:26} provided by {provider}")
        print()

    print(f"{len(ok)} OK, {len(hidden)} not exposed, {len(wrong)} wrong")
    return 1 if wrong else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
