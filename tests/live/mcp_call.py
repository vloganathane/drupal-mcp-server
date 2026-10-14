#!/usr/bin/env python3
"""Call one MCP tool against the live site and print the result.

A driver for operating the site through our own server rather than through
`ddev drush` in a shell. Useful for spot checks, and every call is a live
exercise of the tool it names.

    python tests/live/mcp_call.py jsonapi_resource_types
    python tests/live/mcp_call.py content_create '{"type": "article", "title": "x"}'
    python tests/live/mcp_call.py drush_command '{"command": "pm:list"}'

Runs from the repository root. Exits non-zero if the tool returns an error.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parents[2]
PROJECT = HERE / "drupal-live"
VENV = HERE / "venv"
BASE = os.environ.get("DRUPAL_BASE_URL", "https://drupal-live.ddev.site")


async def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    tool = argv[0]
    args = json.loads(argv[1]) if len(argv) > 1 else {}

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

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            known = {t.name for t in (await session.list_tools()).tools}
            if tool not in known:
                print(f"no such tool: {tool}", file=sys.stderr)
                return 2
            res = await session.call_tool(tool, args, read_timeout_seconds=900)
            text = "".join(getattr(c, "text", "") for c in res.content)
            try:
                print(json.dumps(json.loads(text), indent=2, sort_keys=True))
                return 1 if "error" in json.loads(text) else 0
            except Exception:
                print(text)
                return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
