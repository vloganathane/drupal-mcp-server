#!/usr/bin/env python3
"""Install the modules the sweep found missing -- using our own MCP server.

`tests/live/sweep.py` classifies a tool BLOCKED when the JSON:API resource it
asks for does not exist. Most of those were not bugs: the module providing the
resource simply was not installed. This closes that gap.

Every step is an MCP call, which is the point. `composer_require` and
`drush_command` are the tools an agent would actually use to set a site up,
so running the install through them tests them for real -- including the
failure path, because a module whose dependencies are unmet should come back
as an error rather than as a silent no-op.

    python tests/live/install_modules.py            # all waves
    python tests/live/install_modules.py core       # just one wave
    python tests/live/install_modules.py core contrib

Waves run in dependency order: core first (nothing to download), then contrib
(needs `composer require` before `pm:install` can see the code), then commerce,
then the static-analysis tools the code-quality module shells out to.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parents[2]
# Point the run at another environment (e.g. a Lando site); the server must
# start in the project directory for ddev_*/lando_*/composer_* to resolve.
PROJECT = Path(os.environ.get("SWEEP_PROJECT") or (HERE / "drupal-live"))
VENV = HERE / "venv"
BASE = os.environ.get("DRUPAL_BASE_URL", "https://drupal-live.ddev.site")

# Core modules first: already in the codebase, so `pm:install` alone is enough.
CORE = [
    "media",
    "media_library",
    "comment",
    "contact",
    "language",
    "config_translation",
    "workflows",
    "content_moderation",
]

# Contrib: the package has to be downloaded before Drupal can enable it, so
# each of these is a `composer_require` followed by a `pm:install`.
CONTRIB = [
    "token",
    "pathauto",
    "redirect",
    "metatag",
    "paragraphs",
    "search_api",
    "facets",
    "webform",
    "feeds",
    "graphql",
]

# Commerce is its own wave: a large dependency tree that is worth isolating so
# a failure here does not hide the state of everything before it.
COMMERCE = [
    "commerce",
    "commerce_price",
    "commerce_store",
    "commerce_product",
    "commerce_order",
    "commerce_payment",
    "commerce_shipping",
]

# These are not modules. They are executables that the code-quality tools shell
# out to, so they are composer dev packages and nothing is enabled afterwards.
DEVTOOLS = [
    "phpstan/phpstan",
    "mglaman/drupal-check",
    "squizlabs/php_codesniffer",
    "drupal/coder",
]

# Installing the graphql module does not make /graphql exist: the module ships
# no default server, credentials never reach Drupal without basic_auth, and the
# endpoint refuses every query without the execute permission. All three are
# needed before graphql_query and graphql_schema_get can return anything. The
# block is idempotent so re-running a wave is still a no-op.
GRAPHQL_SETUP = r"""
$s = \Drupal::entityTypeManager()->getStorage('graphql_server');
if (!$s->load('default')) {
  $s->create([
    'id' => 'default', 'name' => 'default', 'label' => 'Default',
    'endpoint' => 'graphql', 'schema' => 'composable',
    'caching' => TRUE, 'batching' => TRUE, 'debug_flag' => 0,
    'disable_introspection' => FALSE,
    'query_depth' => 0, 'query_complexity' => 0,
    'schema_configuration' => ['composable' => ['extensions' => []]],
  ])->save();
}
$role = \Drupal\user\Entity\Role::load('authenticated');
if ($role && !$role->hasPermission('execute default arbitrary graphql requests')) {
  $role->grantPermission('execute default arbitrary graphql requests');
  $role->save();
}
print 'graphql server configured';
"""

WAVES: dict[str, dict[str, list[str]]] = {
    "core": {"install": CORE},
    "contrib": {"require": CONTRIB, "install": CONTRIB},
    # commerce_shipping is deliberately not a dependency of drupal/commerce
    # (shipping is optional), so its package has to be required explicitly -
    # otherwise pm:install fails with the misleading "missing modules
    # commerce_shipping" when the real gap is that no code was downloaded.
    "commerce": {
        "require": ["drupal/commerce", "drupal/commerce_shipping"],
        "install": COMMERCE,
    },
    "devtools": {"require": DEVTOOLS},
    "graphql": {"install": ["basic_auth"], "eval": [GRAPHQL_SETUP]},
}


def steps_for(wave: str) -> list[tuple[str, str, dict]]:
    """Turn a wave into (label, tool, args) steps in the order a user would run."""
    spec = WAVES[wave]
    out: list[tuple[str, str, dict]] = []
    # A bare module machine name is what `pm:install` wants, but composer wants
    # the vendor-qualified package. Every drupal.org contrib project is
    # `drupal/<machine_name>`, so the prefix is derived rather than repeated
    # down the list; devtools already carry their own vendor.
    packages = [p if "/" in p else f"drupal/{p}" for p in spec.get("require", [])]
    # Batched rather than one call per package: each `composer require` re-runs
    # a full dependency resolution, so ten separate calls cost several times
    # what one does. Small batches rather than a single one, so a package that
    # will not resolve for this core version fails only its own group.
    for i in range(0, len(packages), 4):
        batch = packages[i:i + 4]
        out.append((f"composer require {' '.join(batch)}", "composer_require", {
            "package": " ".join(batch),
            "working_dir": ".",
        }))
    if spec.get("install"):
        # One pm:install per module rather than one big batch: a single module
        # with an unmet dependency would otherwise fail the whole batch and
        # leave it unclear which of them were actually enabled.
        for mod in spec["install"]:
            out.append((f"pm:install {mod}", "drush_command", {
                "command": "pm:install",
                "args": [mod],
                "options": {"yes": True},
            }))
    # Configuration steps come after the modules they configure and before the
    # cache rebuild, which is what registers a newly created route.
    for code in spec.get("eval", []):
        out.append((f"{wave}: configure", "drush_php_eval", {"code": code}))
    out.append((f"{wave}: rebuild cache", "cache_rebuild", {}))
    return out


async def call(session: ClientSession, tool: str, args: dict) -> dict:
    res = await session.call_tool(tool, args, read_timeout_seconds=900)
    text = "".join(getattr(c, "text", "") for c in res.content)
    try:
        import json
        return json.loads(text)
    except Exception:
        return {"raw": text}


def resource_types() -> set[str]:
    """Entity types JSON:API currently exposes, straight from the index."""
    import base64
    import json
    import ssl
    import urllib.request

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(
        f"{BASE}/jsonapi/",
        headers={"Accept": "application/vnd.api+json"},
    )
    req.add_header("Authorization", "Basic " + base64.b64encode(b"admin:admin").decode())
    with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
        doc = json.load(r)
    return {k.split("--")[0] for k in doc.get("links", {}) if "--" in k}


async def main(argv: list[str]) -> int:
    if not (PROJECT / "composer.json").exists():
        print(f"no Drupal project at {PROJECT}")
        return 2

    waves = argv or list(WAVES)
    for w in waves:
        if w not in WAVES:
            print(f"unknown wave {w!r}; choose from {', '.join(WAVES)}")
            return 2

    env = dict(os.environ)
    env.update({
        "DRUPAL_BASE_URL": BASE,
        "DRUPAL_USERNAME": "admin",
        "DRUPAL_PASSWORD": "admin",
        "DRUPAL_VERIFY_SSL": "false",
        "MCP_LOG_LEVEL": "ERROR",
        "DRUSH_PATH": os.environ.get("DRUSH_PATH", "ddev drush"),
    })
    params = StdioServerParameters(
        command="sh",
        args=["-c", f"cd {PROJECT} && exec {VENV}/bin/drupal-mcp"],
        env=env,
    )

    before = resource_types()
    print(f"JSON:API exposes {len(before)} entity types before\n")

    passed = failed = 0
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            registered = (await session.list_tools()).tools
            print(f"{len(registered)} tools registered\n")

            for wave in waves:
                print(f"=== wave: {wave} ===")
                for label, tool, args in steps_for(wave):
                    start = time.time()
                    try:
                        result = await call(session, tool, args)
                    except Exception as e:  # a hung or crashing tool
                        failed += 1
                        print(f"  [FAIL] {label:36s} {time.time()-start:6.1f}s  "
                              f"{type(e).__name__}: {str(e)[:80]}")
                        continue
                    elapsed = time.time() - start

                    err = result.get("error") if isinstance(result, dict) else None
                    if err:
                        failed += 1
                        print(f"  [FAIL] {label:36s} {elapsed:6.1f}s  {str(err)[:90]}")
                    else:
                        passed += 1
                        print(f"  [PASS] {label:36s} {elapsed:6.1f}s")
                print()

    after = resource_types()
    gained = sorted(after - before)
    print(f"JSON:API now exposes {len(after)} entity types")
    if gained:
        print("newly exposed:")
        for g in gained:
            print("  +", g)
    print(f"\n{passed} tool steps passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
