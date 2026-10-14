#!/usr/bin/env python3
"""Bring up the local test site using the MCP server's own tools.

The point is to dogfood the package rather than hand-running `ddev` and
`drush` in a shell. Every step below is an MCP call, so bootstrapping the
environment is also a live test of the tools that are hardest to cover
offline: `ddev_setup`, `ddev_start`, `ddev_exec`, `drush_command`,
`drush_php_eval`, and `config_set`.

Each step reports PASS or FAIL, so a broken tool shows up here rather than
silently producing a half-configured site that fails confusingly later.

    python tests/live/bootstrap.py

Prerequisite — the one step that is not an MCP tool, because the package has
no "create a Drupal project from scratch" tool and should not:

    mkdir drupal-live && cd drupal-live
    composer create-project drupal/recommended-project . --no-interaction

Then run this from the repository root.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parents[2]
PROJECT = HERE / "drupal-live"
VENV = HERE / "venv"
BASE = os.environ.get("DRUPAL_BASE_URL", "https://drupal-live.ddev.site")

# Steps in the order a real user would run them. Each is (label, tool, args,
# install_only). `install_only` steps are skipped when Drupal is already
# installed, because `site:install --yes` would reinstall and drop the data.
#
# ddev_setup is the interesting one: it used to write `webroot: web`, which
# DDEV 1.24 silently drops, leaving an empty docroot so nginx serves the
# project root and every request 404s. Running it here catches that.
STEPS = [
    ("write .ddev/config.yaml", "ddev_setup", {
        "project_name": "drupal-live",
        "drupal_version": "10",
        "docroot": "web",
    }, False),
    ("start containers", "ddev_start", {}, False),
    ("install drush", "ddev_exec", {
        "command": "composer require drush/drush --no-interaction",
    }, True),
    ("install Drupal", "drush_command", {
        "command": "site:install",
        "args": ["standard", "--yes", "--db-url=mysql://db:db@db:3306/db"],
        "options": {"site-name": "Live Test Site", "account-name": "admin",
                    "account-pass": "admin"},
    }, True),
    ("grant administrator", "drush_command", {
        "command": "user:role:add",
        "args": ["administrator", "admin", "--yes"],
    }, True),
    ("enable jsonapi + taxonomy", "drush_command", {
        "command": "pm:install",
        "args": ["jsonapi", "taxonomy"],
        "options": {"yes": True},
    }, True),
    # A fresh install leaves JSON:API read-only, which makes every create and
    # update return 405 Method Not Allowed.
    ("allow JSON:API writes", "config_set", {
        "name": "jsonapi.settings",
        "value": {"read_only": 0},
    }, True),
    # The standard profile creates these, but an install that skips its
    # profile does not, and then /jsonapi/node/article 404s with no clue why.
    ("create content types", "drush_php_eval", {
        "code": (
            'foreach (["article" => "Article", "page" => "Basic page"] as $t => $l) {'
            ' if (!\\Drupal\\node\\entity\\NodeType::load($t)) {'
            ' \\Drupal\\node\\Entity\\NodeType::create(['
            ' "type" => $t, "name" => $l, "new_revision" => TRUE])->save();'
            ' print "created $t ";'
            ' }'
            '}'
        ),
    }, True),
]


async def call(session: ClientSession, tool: str, args: dict) -> dict:
    res = await session.call_tool(tool, args, read_timeout_seconds=900)
    text = "".join(getattr(c, "text", "") for c in res.content)
    try:
        import json
        return json.loads(text)
    except Exception:
        return {"raw": text}


def site_is_installed() -> bool:
    """True if Drupal already answers, so the install steps are not re-run.

    `site:install --yes` on an already-installed site does not refuse; it
    reinstalls and drops the data the other live tests depend on.
    """
    import ssl
    import urllib.request

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(f"{BASE}/jsonapi",
                                 headers={"Accept": "application/vnd.api+json"})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
            return r.status == 200
    except Exception:
        return False


async def main() -> int:
    if not (PROJECT / "composer.json").exists():
        print(f"no Drupal project at {PROJECT}")
        print("create one first:")
        print(f"  mkdir {PROJECT.name} && cd {PROJECT.name}")
        print("  composer create-project drupal/recommended-project . --no-interaction")
        return 2

    installed = site_is_installed()

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
            total = (await session.list_tools()).tools
            print(f"{len(total)} tools registered\n")

            for label, tool, args, install_only in STEPS:
                if install_only and installed:
                    passed += 1
                    print(f"  [SKIP] {label:32s}   site already installed")
                    continue
                # ddev_setup refuses to overwrite an existing config, which is
                # correct: calling it with defaults on a working project used
                # to replace the file and take the site down. Skip it when the
                # config is already there so the run stays idempotent.
                if tool == "ddev_setup" and (PROJECT / ".ddev" / "config.yaml").exists():
                    passed += 1
                    print(f"  [SKIP] {label:32s}   config already present")
                    continue

                start = time.time()
                result = await call(session, tool, args)
                elapsed = time.time() - start

                err = result.get("error") if isinstance(result, dict) else None
                if err:
                    failed += 1
                    print(f"  [FAIL] {label:32s} {elapsed:6.1f}s  {str(err)[:90]}")
                else:
                    passed += 1
                    print(f"  [PASS] {label:32s} {elapsed:6.1f}s")

    # Verify the site actually answers, rather than trusting exit codes.
    import ssl
    import urllib.request
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    for path in ("/jsonapi", "/jsonapi/node/article"):
        try:
            req = urllib.request.Request(f"{BASE}{path}",
                                         headers={"Accept": "application/vnd.api+json"})
            with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
                code = r.status
        except Exception as e:
            code = f"{type(e).__name__}"
        status = "PASS" if code == 200 else "FAIL"
        print(f"  [{status}] GET {path:24s} {code}")

    print(f"\n{passed} tool steps passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
