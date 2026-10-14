# Live tests

Offline unit tests cannot catch the bugs that matter most in this package —
they need a real Drupal. Six dead tools, the `ddev_setup` docroot bug, the
empty-body parse error, and the layout_builder tools requesting a resource
that has never existed were all found here and none were caught offline.

## Setup

The Drupal site lives in `drupal-live/` at the repository root and is
gitignored. Create it once:

```bash
mkdir drupal-live && cd drupal-live
composer create-project drupal/recommended-project . --no-interaction
```

Then bring it up using the MCP server's own tools, which doubles as a live
test of `ddev_setup`, `ddev_start`, `ddev_exec`, `drush_command`,
`drush_php_eval`, and `config_set`:

```bash
python tests/live/bootstrap.py
```

`bootstrap.py` skips steps the site already satisfies, so it is safe to
re-run. It will not overwrite an existing `.ddev/config.yaml`, and it will
not re-run `site:install` against an installed site.

Seed the fixtures:

```bash
cd drupal-live
ddev exec bash -c 'cat > /tmp/seed.php' < ../tests/live/seed.php
ddev drush php-script /tmp/seed.php
```

## Running

```bash
python tests/live/smoke_test.py         # 9 end-to-end cases, ~30s
python tests/live/layout_builder_test.py  # 10 Layout Builder cases, ~60s
python tests/live/sweep.py        # every tool, ~30 min
python tests/live/sweep.py composer_  # only tools whose name contains that
```

Both need `venv/` with the package installed (`pip install -e ".[dev]" mcp`)
and `ddev` running. They start the MCP server from `drupal-live/`, because the
`ddev_*`, `lando_*` and `composer_*` tools run in their own working directory
and `ddev drush` only resolves inside the project.

## What each file is for

| File | Purpose |
|------|---------|
| `bootstrap.py` | Bring the site up using MCP tools rather than hand-run `ddev`/`drush` |
| `seed.php` | Idempotent fixtures: admin role, a sacrificial `sweeptarget` user, a `tags` vocabulary with a term, two article nodes |
| `smoke_test.py` | Nine cases covering the operations a user actually reaches for |
| `layout_builder_test.py` | Ten cases for the six `layout_builder_*` tools, including an override create/revert round trip |
| `sweep.py` | Calls every registered tool and classifies the result |

## Verdicts

`DEAD` is reserved for product bugs. Anything environmental lands elsewhere,
so a missing module never hides a broken tool:

| Verdict | Meaning |
|---------|---------|
| `OK` | returned usable data |
| `REJECTED` | the tool answered, and the answer was a refusal or lookup miss |
| `UPSTREAM` | needs a module this site does not have (Commerce, Webform, ...) |
| `BLOCKED` | needs a local binary that is not installed (phpstan, ollama, ...) |
| `DEAD` | the tool itself is broken |
| `SKIPPED` | controls the environment the sweep runs against |

## Things that will bite you

- **The sweep calls `ddev_stop`.** It genuinely stops the project, which takes
  the site down and makes every tool after it time out instead of reporting.
  `ENV_CONTROL` skips those tools for this reason. Do not remove it.
- **`pick_live_nid` returns an int.** JSON:API serialises
  `drupal_internal__nid` as a number, but tools declare `nid: str`, so
  pydantic rejects the call with `string_type` before the body runs. The
  harness coerces it to `str`.
- **Union parameters arrive as `anyOf`, not `type`.** FastMCP emits
  `list[str] | None` as `{"anyOf": [...]}` with no top-level `type`. Reading
  only `type` sends `"sweep_value"` where a list is required and FastMCP
  rejects the call. `resolve_schema` handles it.
- **A fresh install leaves JSON:API read-only.** Every create and update then
  returns 405 Method Not Allowed. `bootstrap.py` sets `read_only: 0`.
- **DDEV's key is `docroot`, not `webroot`.** DDEV 1.24 silently drops an
  unrecognised key, so an empty docroot makes nginx serve the project root and
  every request 404s.
