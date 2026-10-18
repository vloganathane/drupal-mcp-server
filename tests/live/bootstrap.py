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
import json
import os
import ssl
import subprocess
import time
import urllib.request
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parents[2]
PROJECT = HERE / "drupal-live"
VENV = HERE / "venv"
BASE = os.environ.get("DRUPAL_BASE_URL", "https://drupal-live.ddev.site")


def live_nid() -> str:
    """Return a real node id from the site, creating one if it has none.

    Hardcoding an id produced false failures: the sweep deletes what it
    touches, so a test naming node 3 fails once node 3 is gone even though the
    tool under test answered correctly - and it did, "No node with id 3". The
    id is read instead so that cannot recur, and a node is created when the
    collection comes back empty so a suite run after an emptying sweep fails on
    something real rather than on the absence of a fixture.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(
        f"{BASE}/jsonapi/node/article",
        headers={"Accept": "application/vnd.api+json"},
    )
    doc = json.load(urllib.request.urlopen(req, context=ctx))
    if "data" not in doc:
        # An error document is a site problem, not a missing fixture; creating
        # a node here would hide it behind a confusing later failure.
        raise RuntimeError(f"JSON:API returned no collection: {json.dumps(doc)[:300]}")
    rows = doc["data"] or []
    if rows:
        return str(rows[0]["attributes"]["drupal_internal__nid"])
    return _provision_node()


def _provision_node() -> str:
    """Create an article through Drush and return its id."""
    php = (
        "$n = \\Drupal\\node\\Entity\\Node::create(["
        "'type' => 'article', 'title' => 'live test fixture', 'status' => 1]); "
        "$n->save(); print json_encode(['nid' => (int) $n->id()]);"
    )
    proc = subprocess.run(
        ["ddev", "drush", "php:eval", php],
        cwd=PROJECT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "no article to test against and could not create one: "
            + (proc.stderr or proc.stdout).strip()[:300]
        )
    return str(json.loads(proc.stdout.strip())["nid"])

# Steps in the order a real user would run them. Each is (label, tool, args,
# install_only). `install_only` steps are skipped when Drupal is already
# installed, because `site:install --yes` would reinstall and drop the data.
#
# ddev_setup is the interesting one: it used to write `webroot: web`, which
# DDEV 1.24 silently drops, leaving an empty docroot so nginx serves the
# project root and every request 404s. Running it here catches that.
STEPS = [
    # project_name is "." because the server itself runs inside PROJECT
    # (main() spawns it with `cd {PROJECT}`): passing "drupal-live" here
    # resolved against the server's cwd and nested a second
    # drupal-live/drupal-live/.ddev/config.yaml, which ddev start then
    # could not find - the first CI run failed exactly there.
    ("write .ddev/config.yaml", "ddev_setup", {
        "project_name": ".",
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
            # Entity, not entity: PSR-4 resolves the path from the class name
            # verbatim, so the lowercase spelling only ever loaded by
            # accident on a case-insensitive filesystem and fails as
            # "class not found" on Linux CI.
            ' if (!\\Drupal\\node\\Entity\\NodeType::load($t)) {'
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

    Drush inside the container decides this, never the public URL: a dev
    router can 404 every path (DDEV's does after a reboot) while the site
    is perfectly installed, and trusting that URL re-ran site:install
    against a live site and wiped its data. A project whose containers are
    not up yet - a fresh CI job - fails the command and reads as not
    installed, which is exactly right at that point.
    """
    import subprocess

    try:
        proc = subprocess.run(
            ["ddev", "drush", "status", "--fields=bootstrap"],
            cwd=PROJECT, capture_output=True, text=True, timeout=300,
        )
    except Exception:
        return False
    return proc.returncode == 0 and "Successful" in proc.stdout


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

                err = None
                if isinstance(result, dict):
                    err = result.get("error")
                    # ddev_*/lando_* answer with returncode/stdout/stderr and
                    # never an "error" key - the same gotcha sweep.classify
                    # documents - so a non-zero exit used to print PASS here
                    # and hide exactly which step really broke.
                    if (
                        err is None
                        and isinstance(result.get("returncode"), int)
                        and result["returncode"] != 0
                    ):
                        msg = (result.get("stderr") or "").strip() or (
                            result.get("stdout") or ""
                        ).strip()
                        err = f"returncode {result['returncode']}: {msg}"
                if err:
                    failed += 1
                    print(f"  [FAIL] {label:32s} {elapsed:6.1f}s  {str(err)[:240]}")
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
