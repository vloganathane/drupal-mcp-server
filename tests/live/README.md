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

Found once the modules were installed, and still not catchable offline:

- **a resource name that does not exist in Drupal**, which is indistinguishable
  from a missing module. `views_list` asked for `views_view`; the entity type
  has been `view` since Drupal 8, so all six views tools 404'd on a site with
  Views installed and healthy, and the sweep read three of them as BLOCKED and
  three as ordinary lookup misses. `resource_check.py` asks Drupal for the
  entity types it actually knows, which found eleven more the same way --
  `moderation_state`, `search_api_facet`, `language`, `metatag_config` and six
  names that are not entity types at all;
- **`options={"yes": True}`**, which `drush_command` rendered as `--yes=True`.
  Drush flags take no value, so it was refused outright: installing a module
  through the tool failed every time and reported success. A `False` was worse,
  because it passed the bare flag, silently suppressing confirmation on
  destructive commands;
- **the host `composer` resolving a DDEV project's dependencies against the
  host's PHP.** It locked in a `doctrine/collections` release needing PHP 8.4
  for a container running 8.3, and Composer's platform check then aborted every
  subsequent request, taking the site down;
- **`langcode: "en"` in create payloads**, harmless until a second language
  makes the field permission-gated, after which every create answers 403;
- **twelve tools that refused, or had never been written at all.** The five
  `moderation_transition_*` tools read `$wf->get("transitions")`, a key the
  workflow entity has never had — the transitions live on
  `Workflow::getTypePlugin()->getTransitions()` — so `list` answered
  `count: 0` against a five-transition workflow while `get` reported "No
  transition with id 7". The four `interface_translation_*` tools read
  `TranslationString::getLanguage()` and `getTranslation()`, methods that do
  not exist on that class, and the three `webform_handler_*` tools answered
  `absent_entity` because they had never been written. All twelve now round
  trip against the live site, with the misses pinned offline;
- **PHP written by way of `json.dumps`.** Structured values interpolated into
  `drush php:eval` were serialised as JSON, which is not PHP: there is no
  `\uXXXX` escape there so non-ASCII mangles silently, `$` interpolates, and
  `{"k":1}` is a parse error. `_utils.php_text()` and `php_json()` carry them
  as base64 instead.

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

The sweep needs the modules its tools target, which a standard install does not
include. Install them through the MCP server's own tools rather than by hand,
which is also a live test of `composer_require` and `drush_command`:

```bash
python tests/live/install_modules.py            # every wave
python tests/live/install_modules.py core       # just one wave
```

It runs in dependency order — core, contrib, commerce, then the static-analysis
binaries — one `pm:install` per module so a single unmet dependency cannot hide
which of them landed, and prints the entity types JSON:API exposes before and
after. Re-running is safe: composer resolves nothing new and installing an
installed module is a quick no-op.

Installing `graphql` is not enough to make `/graphql` exist. The module ships
no default server, so the endpoint 404s until a `graphql_server` config entity
is created, `basic_auth` is enabled for credentials to reach Drupal at all, and
`execute default arbitrary graphql requests` is granted to `authenticated`.
`python tests/live/install_modules.py graphql` does all three through the
server's own tools. A site without them makes `graphql_query` and
`graphql_schema_get` report a missing server, which is what those tools now say
instead of returning a bare 404.

## Running

```bash
python tests/live/smoke_test.py           # 9 end-to-end cases, ~30s
python tests/live/layout_builder_test.py  # 10 Layout Builder cases, ~60s
python tests/live/queue_test.py           # 18 cron/queue cases, ~60s
python tests/live/filter_check.py         # every hard-coded filter, ~5s
python tests/live/resource_check.py       # every resource name, ~10s
python tests/live/install_modules.py      # the modules the tools assume, ~10 min
python tests/live/sweep.py                # every tool, ~30 min
python tests/live/sweep.py composer_      # only tools whose name contains that
python tests/live/mcp_call.py content_list '{}'   # one call, for spot checks
```

These need `venv/` with the package installed (`pip install -e ".[dev]" mcp`)
and `ddev` running. They start the MCP server from `drupal-live/`, because the
`ddev_*`, `lando_*` and `composer_*` tools run in their own working directory
and `ddev drush` only resolves inside the project.

## What each file is for

| File | Purpose |
|------|---------|
| `bootstrap.py` | Bring the site up using MCP tools rather than hand-run `ddev`/`drush` |
| `install_modules.py` | Install the modules the tools assume, through `composer_require` and `drush_command` |
| `mcp_call.py` | Call one tool and print the result; every call is a live exercise of the tool it names |
| `seed.php` | Idempotent fixtures: admin role, a sacrificial `sweeptarget` user, a `tags` vocabulary with a term, two article nodes |
| `smoke_test.py` | Nine cases covering the operations a user actually reaches for |
| `layout_builder_test.py` | Ten cases for the six `layout_builder_*` tools, including an override create/revert round trip |
| `queue_test.py` | Eighteen cases for the six cron/queue tools, including a cross-queue `item_id` delete that core's own `deleteItem()` would get wrong |
| `filter_check.py` | Sends every hard-coded JSON:API filter to the site and fails on a 400, which is what made two tools dead on every site |
| `resource_check.py` | Asks Drupal which entity types it knows and flags any resource name our tools ask for that cannot exist |
| `sweep.py` | Calls every registered tool and classifies the result |

## Verdicts

`DEAD` is reserved for product bugs. Anything environmental lands elsewhere,
so a missing module never hides a broken tool:

| Verdict | Meaning |
|---------|---------|
| `OK` | returned usable data |
| `REJECTED` | the tool answered, and the answer was a refusal or lookup miss |
| `UPSTREAM` | needs a module or subsystem this site does not have |
| `BLOCKED` | needs a local binary that is not installed (phpstan, ollama, ...) |
| `DEAD` | the tool itself is broken |
| `SKIPPED` | controls the environment the sweep runs against |

## Which ids the sweep sends

Every parameter ending in `id` used to be answered with the fixture node's id,
so `view_id`, `menu_id` and `webform_id` were all sent one node number and the
tools answered a lookup miss. That was 84 of 174 refusals in the run before it
was fixed — not tools refusing, but the harness asking the wrong question, and a
miss says nothing about whether a tool works. Of the 367 tools:

- **192** declare no `id`-shaped parameter at all;
- **93 read-only** tools are handed a real id for their own resource, from
  `FIXTURE_ID` and `FIXTURE_BY_TOOL`. Where one parameter name covers several
  resources — `config_id` is a field config, a metatag config or a search index
  depending on who is asking — the tool's own name decides;
- **82 mutating** tools deliberately keep junk ids. `views_update` with a real
  view id would save the view back with the arguments the harness synthesised,
  and every later `views_execute` would run against a view this run broke, so
  structural writes are refused rather than applied;
- **8 read-only** tools still get junk because this site has no such entity to
  name: `analyze_node_ids`, `acquia_site_id`, `menu_link_id`, `media_id`,
  `media_derivative_id`, `commerce_product_id`, `commerce_order_id` and
  `commerce_gateway_id`.

`MUTATING` decides which side a tool falls on, and it is worth reading before
changing it: it is the difference between a sweep that measures the tools and
one that dismantles the site it is measuring.

## Where the sweep stands

Against the provisioned site, on the run that follows the module install, the
resource-name fixes and the filter fixes:

| | before | after |
|---|---|---|
| OK | 156 | **181** |
| BLOCKED | 71 | **5** |
| DEAD | 0 | **0** |

25 tools that could not be reached at all now run, and 41 reach Drupal and are
turned away with a reason instead of stopping at a 404. No tool that used to
work now fails, and nothing is dead.

What is left is five, all explained:

- `feeds_feed_list` / `feeds_feed_create` — JSON:API exposes no `feeds_feed`
  resource until a feed type exists with a `feeds_item` field on its target
  bundle, which needs field configuration on that bundle and so cannot be
  provisioned by installing a module
- `moderation_state_list` / `moderation_state_create` — `content_moderation_state`
  is never exposed through JSON:API, by Drupal's design
- `split_config` — needs a `./config/sync` directory, which the site does not have

The one `UPSTREAM` is `revision_delete`: JSON:API has no revision collection
endpoint, so there is nothing to delete through it.

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
- **The site is multilingual on purpose.** English and French are both enabled,
  which makes `langcode` a permission-gated field and keeps the "not allowed to
  POST the selected field (langcode)" bug caught. A 403 on a create is not
  something to fix by removing the second language.
- **`composer_*` resolves inside the container.** `_container_composer` picks
  `ddev composer` when the project has a `.ddev` directory. The host composer
  resolves against the host's PHP, which locked in a `doctrine/collections`
  release the container's 8.3 could not run, and Composer's platform check then
  aborted every request.
- **The site's links are the site's idea of the site.** Drupal builds every
  `href` and redirect from the scheme and host it saw the request arrive on,
  which need not be the ones you are using: behind a proxy, or reached on a
  container's published port without DDEV's router in front, it answers `http://`
  while you are on HTTPS. Following one of those sends plain HTTP to a TLS
  listener and nginx answers **400 "The plain HTTP request was sent to HTTPS
  port"** — which killed a whole sweep run before it called a single tool, and
  separately turned a successful login into a reported failure. `_reanchor()`
  puts every followed link back on `BASE`'s origin, and `SessionAuth.login()`
  no longer follows the login redirect at all. If `ddev start` fails its health
  check and never creates the router, the site is still reachable at the
  container's published port: `docker port ddev-drupal-live-web`, then
  `DRUPAL_BASE_URL=https://127.0.0.1:<port>`. That is what the sweep in this
  directory was run against.
- **JSON:API cannot be asked "does this node exist".** The resource *name* in
  the index (`node--article`) is not its path (`/jsonapi/node/article`), and a
  row is addressed by uuid rather than by `drupal_internal__nid`, so neither
  `/jsonapi/node--article/7` nor `/jsonapi/node/article/7` answers the question
  — both 404 for nodes that exist, which made the fixture look permanently gone
  and would have had it re-provisioned on every check. The answer is a
  `filter[drupal_internal__nid]` across the bundles the index advertises.
