#!/usr/bin/env python3
"""Nine end-to-end cases against a live Drupal site.

This is the fast check: the sweep covers all 366 tools and takes ~30 minutes,
this covers the operations a user actually reaches for and takes ~5.

    python tests/live/smoke_test.py

Each case prints the tool, how long it took, and the first 300 characters of
what came back. Cases that raise are reported rather than aborting the run, so
one failure does not hide the rest.
"""

from __future__ import annotations

import asyncio
import json
import os
import ssl
import time
import urllib.request
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parents[2]
BASE = os.environ.get("DRUPAL_BASE_URL", "https://drupal-live.ddev.site")
VENV = HERE / "venv"


def live_nid() -> str:
    """Read a real node id from the live site rather than hardcoding one.

    Hardcoding produced two false failures after a sweep deleted the node the
    test happened to name; the tool was correct and the fixture was not.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(
        f"{BASE}/jsonapi/node/article",
        headers={"Accept": "application/vnd.api+json"},
    )
    data = json.load(urllib.request.urlopen(req, context=ctx))
    return str(data["data"][0]["attributes"]["drupal_internal__nid"])


async def main() -> int:
    nid = live_nid()
    print(f"using live node {nid}\n")
    env = dict(os.environ)
    env.update({
        "DRUPAL_BASE_URL": BASE,
        "DRUPAL_USERNAME": "admin",
        "DRUPAL_PASSWORD": "admin",
        "DRUPAL_VERIFY_SSL": "false",
        "MCP_LOG_LEVEL": "ERROR",
        "DRUSH_PATH": "ddev drush",
    })
    # The server must start in the DDEV project directory: `ddev drush` only
    # resolves inside the project.
    project = HERE / "drupal-live"
    params = StdioServerParameters(
        command="sh",
        args=["-c", f"cd {project} && exec {VENV}/bin/drupal-mcp"],
        env=env,
    )

    cases = [
        ("query_nodes", {"bundle": "article"}),
        ("get_node", {"nid": nid}),
        ("list_users", {}),
        ("list_vocabularies", {}),
        # create_node takes a `fields` dict, not a bare title: the tool wraps
        # it into JSON:API's {data: {type, attributes}} shape itself.
        ("create_node", {"bundle": "article", "fields": {"title": "Smoke Test Node"}}),
        ("update_node", {"nid": nid, "fields": {"title": "Renamed by smoke test"}}),
        ("create_term", {"vid": "tags", "name": "smoke term"}),
        ("list_terms", {"vid": "tags"}),
        ("get_user_roles", {"uid": "2"}),
    ]

    passed = failed = 0
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            print(f"{len(tools)} tools registered\n")

            for name, args in cases:
                start = time.time()
                try:
                    res = await session.call_tool(name, args, read_timeout_seconds=240)
                    text = "".join(getattr(c, "text", "") for c in res.content)
                    # FastMCP's validation errors are human-readable text, not
                    # JSON; parsing them blindly raised JSONDecodeError and hid
                    # the real message.
                    try:
                        payload = json.loads(text)
                    except Exception:
                        payload = {"error": text[:400]}
                    if isinstance(payload, dict) and payload.get("error"):
                        failed += 1
                        status = "FAIL"
                    else:
                        passed += 1
                        status = "PASS"
                except Exception as e:
                    failed += 1
                    status = "FAIL"
                    text = f"{type(e).__name__}: {e}"
                    payload = text

                elapsed = time.time() - start
                preview = json.dumps(payload)[:200] if not isinstance(payload, str) else payload[:200]
                print(f"  [{status}] {name:22s} {elapsed:5.1f}s  {preview[:120]}")

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
