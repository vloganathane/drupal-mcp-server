# Live tests

Offline unit tests cannot catch the bugs that matter most in this package —
they need a real Drupal. Found here, none of them offline:

- a SQL injection in `db_query`, proved by a `SELECT 1; DROP TABLE x` that
  passed the `startswith("SELECT")` guard and actually dropped the probe table;
- Drush arguments being shlex-split, so `db_tables`, `db_query`, `db_count`,
  `drush_php_eval` and every `ev` tool failed with "Too many arguments";
- those same failures being reported as **OK**, because a failed Drush run
  carries no `error` key and the harness — and any real MCP client — read
  `data: {}` as an empty success;
- two tools filtering on fields Drupal does not expose (`filter[name]` on
  `user_role`, `filter[menu]` on `menu_link_content`), which meant a 400 on
  every call on every site;
- three scheduler tools that could never have worked: `cron_list` asked for
  Drupal 7's `drupal_get_cron_jobs()` (gone since Drupal 8), `queue_create`
  put a shell escape into PHP that never sees a shell and died with a
  ParseError, and `queue_delete` passed Drush a second argument on all three
  paths when `queue:delete` accepts exactly one — so every branch answered
  "Too many arguments";
- `queue:delete` resolving only *registered* queue services, answering "Queue
  not found" for a queue this server had just created;
- the `ddev_setup` docroot key, the empty-body parse error, and the six
  `layout_builder_*` tools requesting a JSON:API resource that has never
  existed.

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
python tests/live/smoke_test.py           # 9 end-to-end cases, ~30s
python tests/live/layout_builder_test.py  # 10 Layout Builder cases, ~60s
python tests/live/queue_test.py           # 18 cron/queue cases, ~60s
python tests/live/filter_check.py         # every hard-coded filter, ~5s
python tests/live/sweep.py                # every tool, ~30 min
python tests/live/sweep.py composer_      # only tools whose name contains that
```

These need `venv/` with the package installed (`pip install -e ".[dev]" mcp`)
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
| `queue_test.py` | Eighteen cases for the six cron/queue tools, including a cross-queue `item_id` delete that core's own `deleteItem()` would get wrong |
| `filter_check.py` | Sends every hard-coded JSON:API filter to the site and fails on a 400, which is what made two tools dead on every site |
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
- **A failure may arrive as `returncode`, never as `error`.** Drush results
  carry their reason in `stderr` and no `error` key. `classify` checks
  `returncode != 0` for this reason: without it, the first full sweep reported
  `db_tables`, `db_query`, `db_count` and `drush_php_eval` as **OK** while
  Drush was answering "Too many arguments" on every one of them, and the
  headline was "0 dead tools" when there were at least five.
- **A fresh install leaves JSON:API read-only.** Every create and update then
  returns 405 Method Not Allowed. `bootstrap.py` sets `read_only: 0`.
- **DDEV's key is `docroot`, not `webroot`.** DDEV 1.24 silently drops an
  unrecognised key, so an empty docroot makes nginx serve the project root and
  every request 404s.
