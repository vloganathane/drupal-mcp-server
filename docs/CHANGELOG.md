# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Wave 3 of the drupal-scout-mcp port — 4 export tools (404 total, 40
  modules): `export_nodes`, `export_users`, `export_media`,
  `export_taxonomy` write CSV (UTF-8 with BOM) or Excel files
  (`openpyxl`, new runtime dependency) and return only the path,
  row/column counts, size, and a three-row preview. Destination paths are
  confined to the Drupal root, the system temp directory, or the home
  directory; data is paged per bundle over JSON:API (never through the
  shared merged offset, which skips rows), and taxonomy usage counts come
  from one validated `GROUP BY` query per field storage targeting
  taxonomy terms, with unreadable tables reported in a note instead of
  failing the export (and a `safe_to_delete` verdict withheld entirely
  whenever the counts are incomplete). Entries with no internal id —
  Drupal's uid-0 anonymous user serves only a display_name — are skipped
  and counted as `skipped_without_id`, and an unreadable status stays
  empty in the CSV rather than being presented as "blocked"
- `sql_output`/`sql_rows` moved from the analysis module into `_utils` so
  the export tools parse `drush sql:query` text the same way
- Wave 2 of the drupal-scout-mcp port — 8 tools (400 total, 39 modules):
  - Status section (4): `status_report` (drush core:requirements, severity
    filter), `database_updates` (read-only pending DB updates),
    `available_updates` (composer outdated with dev filtering and a
    security-only mode intersected with composer audit), `health_check`
    (Drush, database, JSON:API, and module probes with a fix per failure)
  - Analysis: `find_entity_references` (bundles whose reference fields
    target an entity type, via JSON:API field config), `search_entities`
    (escaped LIKE search across six entity tables), `find_entity_by_path`
    (route or path-alias resolution to an entity)
  - Config: `config_status` (read-only active vs sync comparison)
- `run_composer` gained a `tail` argument so tools that parse full JSON
  documents (`composer outdated`) are not truncated

## [0.2.0] - 2026-10-16

### Security

- Fix command injection vulnerabilities in code audit and security audit tools
- Fix SQL injection in database query tools
- Fix path traversal in media upload tool
- Add input validation for URLs, queue names, and file paths
- Add authentication check to /mcp/tools/list endpoint

### Added

- Add `drupal-mcp install`, a self-installer that registers the server with
  local MCP clients (Claude Code, Claude Desktop, Cursor, Codex CLI,
  OpenCode, Windsurf, Pi, Hermes Agent, OpenClaw), with `--print`/`--json`
  for scripted setup and an AI Coding Agents guide
- Add `module_issues_search`, `module_popular`, and `module_recommendation`
  (client-side issue-queue relevance scoring, usage-ranked module lists by
  category, local-index + drupal.org recommendations), plus the `DRUPAL_ROOT`
  and `DRUPAL_MODULES_PATH` settings for local codebase analysis
- Add a local codebase index with 12 `codebase_*` tools: functionality
  search, module inventory/descriptions, unused and redundant module
  detection, hook implementation lookup, and safe module file/tree/function
  reading (all reads confined to `DRUPAL_ROOT`)
- Add `moderation_transition_delete`, giving `moderation_transition_create` the
  counterpart it never had. The tool count is now 367
- Add Lando support to SiteManager
- Add subprocess timeout to DrushClient
- Add OAuth token fetching to AuthManager
- Create shared tools/_utils.py with ensure_dict, validate_pagination, build_pagination_params
- Add pagination validation to list tools
- Add input validation to accessibility and performance tools
- Add LICENSE, CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md
- Add GitHub issue and PR templates

### Changed

- Correct what the sweep asks for, not just how it reads the answer. Every
  parameter ending in `id` had been answered with the fixture node's id, so
  `view_id`, `menu_id`, `webform_id` and eighty-odd others were all sent one
  node number and answered a lookup miss: **84 of 174 refusals** in the run
  before this were the harness asking the wrong question, not tools refusing,
  and a miss says nothing about whether a tool works. Of 367 tools, 192 declare
  no id-shaped parameter, 93 read-only ones now get a real id for their own
  resource — with the tool's own name deciding where one parameter covers
  several, since `config_id` is a field config, a metatag config or a search
  index depending on who is asking — and 82 mutating ones deliberately keep
  junk ids, because `views_update` with a real view id would save the view back
  with the harness's synthesised arguments and every later `views_execute`
  would then run against a view this run broke. The remaining 8 read-only tools
  keep junk because the site has no such entity to name. The fixture node also
  re-checks and re-provisions itself: `delete_node` runs mid-sweep and took the
  node with it, which alone 404'd `revision_list`, `revision_get`,
  `revision_revert`, `revision_diff`, `translation_status`, `translation_add`,
  `moderation_transition_execute`, `layout_builder_override_remove` and
  `accessibility_aria_validate`
- Keep `feeds_log_list` an explicit refusal rather than implement it. Feeds 3.x
  has no log table, no `feeds*` service and no log entity to read, so there is
  nothing behind it to query; the tool names `imports_import_status`, which does
  answer, instead of returning an empty list that would read as "no log entries"
- Definitive full re-sweep (OK 195 / REJECTED 156 / BLOCKED 7 /
  UPSTREAM 4 / DEAD 0 / SKIPPED 5, 367 total); no tool that used to work
  regressed and nothing is dead. Harness follow-up fixes (`entity_id` and
  revision-id handling) pushed six more tools past their lookup so they reach
  their own logic, where they report honestly.

- Re-sweep all 366 tools against the provisioned site. BLOCKED fell from 71 to
  5, OK rose from 156 to 181, and nothing is dead. 25 tools that could not be
  reached at all now run; 41 reach Drupal and are turned away with a reason
  instead of stopping at a 404. The five still BLOCKED are two `feeds_feed`
  tools needing a feed type with a `feeds_item` field, two `moderation_state`
  tools for a resource Drupal never exposes, and `split_config` needing a
  `./config/sync` directory. The one UPSTREAM is `revision_delete`, since
  JSON:API has no revision collection endpoint
- Correct the sweep's own accounting. Six tools — `translation_add`,
  `translation_update`, the three `interface_translation_*` tools and
  `config_translation_add` — were reported OK on every run while never being
  called once. When arguments fail FastMCP's validation the answer is prose
  rather than JSON, and nothing in the classifier matched it, so the
  fall-through said pass; the server logged `missing_argument` for each and
  the report showed a green result. A refused call now counts as refused,
  through the SDK's own `isError` signal rather than a guess at wording. The
  sweep also stopped filling `langcode` with a junk value (JSON:API
  write-protects that field on a multilingual site whatever it says, so
  `create_term` answered 403 about a permission instead of running),
  started giving `ddev_exec` a command the container has, gave
  `drush_watchdog` the enum and the number drush wants, and names a queue
  that exists
- Provision the live test site with the modules the tools assume are there:
  media, comment, contact, language, config_translation, workflows,
  content_moderation and commerce plus its submodules from core and contrib,
  and token, pathauto, redirect, metatag, paragraphs, search_api, facets,
  webform, feeds and graphql from drupal.org, with phpstan, drupal-check,
  phpcodesniffer and coder for the code-quality tools. Drupal's entity types
  went from 26 to 78 and the JSON:API index from 27 resources to 76, which
  turned most of the sweep's BLOCKED bucket into a real verdict. The site is
  also multilingual now -- English and French -- because a single-language site
  cannot exercise translation behaviour, and that is what surfaced the langcode
  bug below
- Add three live suites. `tests/live/install_modules.py` provisions the modules
  the sweep needs using the server's own `composer_require` and `drush_command`
  tools, so bootstrapping the site is also a test of them; `resource_check.py`
  asks Drupal for the entity types it knows and flags any resource name our
  tools ask for that cannot exist, which is how the `views_view` and
  `moderation_state` bugs were found; `mcp_call.py` is a one-call driver for
  operating the site through the server instead of a shell

- Gate CI coverage on the code testable offline (non-tool core ≥70%) instead of
  the total: 86% of statements live in the tool modules, which only a live sweep
  can exercise, so a single total threshold is unreachable by construction.
  `coverage.xml` is now actually generated, which the Codecov step already
  required with `fail_ci_if_error: true`
- Extend `layout_builder_override_remove` with an optional `entity_id`, since an
  override belongs to an entity and the old signature could never name one
- Document what live testing found, and how a failure arrives, in
  `tests/live/README.md` and the README's Development section
- Extract _ensure_dict from 35+ tool modules into shared utility
- Remove duplicate service implementations (ai.py, migration.py, site.py)
- Clean up unused imports across all tool modules
- Update ARTIFACT.md to reflect actual project state

### Fixed

- Make an issued OAuth token worth issuing. HTTP transport with OAuth enabled
  refused everyone: `load_access_token` returned the dict the token was stored
  in where the declared type is FastMCP's `AccessToken`, so the first thing the
  bearer middleware did with a good token -- `auth_info.expires_at` -- raised
  `AttributeError: 'dict' object has no attribute 'expires_at'` and the request
  was refused exactly as a forged one would be. That made the defect invisible
  by construction, because the fail-closed path and the fail-for-everyone path
  are the same 401: the only OAuth behaviour anyone had ever observed was the
  reassuring one, and the 401 that read as security working was also masking an
  unusable transport. `expires_at` was stored as a float from `time.time()`
  while `AccessToken.expires_at` is an int, so pydantic would have refused it
  regardless. Verified three ways -- unit tests over authorize/exchange/load,
  an ASGI test against FastMCP's real HTTP app (401 unauthenticated, 200 for
  the issued token, 401 for a forged one), and a replay of the old
  implementation that reproduces the AttributeError
- Implement twelve tools that refused or had never been written. The five
  `moderation_transition_*` tools all read `$wf->get("transitions")`, a key the
  workflow entity has never had — transitions live on
  `Workflow::getTypePlugin()->getTransitions()` — so `list` answered
  `count: 0` against a five-transition workflow, which reads as a pass because
  an empty list is not an error, `get` reported "No transition with id 7" for a
  transition present by name, and `execute`, `create` and the new `delete` were
  unreachable behind the same mistake. The four `interface_translation_*` tools
  read `TranslationString::getLanguage()` and `getTranslation()`, methods that
  class does not have; they now go through `locale.storage`, and a live round
  trip verified the list (13666 French rows, with search and context filters),
  add, update and delete, including a source string carrying a non-ASCII
  character and a `$`. Writing a translation also dispatches
  `LocaleEvents::SAVE_TRANSLATION` through `_locale_refresh_translations()`,
  which invalidates the `locale` cache tag every `LocaleLookup` row depends on
  — `invalidateByPrefix` and `cache_clear_all` do not exist in Drupal 11. The
  three `webform_handler_*` tools answered `absent_entity` because they had
  never been written; they now use `plugin.manager.webform.handler` with
  `Webform::addWebformHandler` / `updateWebformHandler` / `deleteWebformHandler`,
  take `webform_id` to disambiguate a handler id that is unique per webform
  rather than site-wide, replace configuration keys whole so omitted ones keep
  their current values, and locate handlers through
  `getHandlers()->getInstanceIds()` instead of `Webform::getHandler()`, which
  throws `PluginNotFoundException` for an unseen id rather than returning NULL.
  A `contact` form started this with two handlers and ended with two after a
  full create/update/delete — the point of a round trip
- Hand structured values to `php:eval` as base64 rather than as JSON, which is
  not PHP: it emits `\uXXXX` and PHP has no such escape, so non-ASCII mangles
  silently; `$` interpolates into the code; and `{"k":1}` is a parse error.
  `_utils.php_text()` and `php_json()` carry a string as `base64_decode(...)`
  and an array as `json_decode(base64_decode(...), TRUE)`
- Stop chasing the login redirect to a URL the site invented. Drupal answers a
  good login with 303 to the account page, built from the scheme and host it
  saw the request arrive on, so when the site reported itself as plain `http`
  while the client was on HTTPS the redirect was fetched as HTTP against a TLS
  port, nginx answered 400, and the session cookie that same response had just
  issued was discarded — leaving only a startup warning. Every write then fell
  back to basic auth, which Drupal's mutating endpoints reject, on any site
  whose self-issued URL disagrees with the client's behind a proxy or a
  misconfigured base_url. The POST is no longer followed, because only its
  status and its cookie were ever wanted; bad credentials still fail, since
  Drupal refuses them with 200 and no cookie
- Make the sweep follow the site's links on the origin it was given. Drupal
  answers `http://` when reached through a port-mapped HTTPS endpoint, and the
  harness followed those verbatim — plain HTTP to a TLS listener, which nginx
  refuses with 400 — so a whole run died before calling a single tool.
  `filter_check.py` hardcoded its base URL while every other live script honours
  `DRUPAL_BASE_URL`, so it could not be pointed at all
- Ask whether a node exists in a way JSON:API can answer. The check built the
  resource *name* into the path (`/jsonapi/node--article/7`, where the resource
  lives at `/jsonapi/node/article`) and asked for an internal id where rows are
  addressed by uuid, so it 404'd for nodes that exist and reported every fixture
  as gone — which would have had the harness re-provisioning on every check
  instead of only when `delete_node` removed one
- Make three tools answer with the reason instead of a bare error.
  `views_execute` could never have run: it asked for a `views.views` service
  that does not exist (the executable is built from the view's config entity by
  `views.executable`), read the row's entity through a magic property that
  `isset()` always reports as absent, and took no care over the display. It now
  loads the view, checks the display against the ones the view actually has --
  reporting the rest when the caller's is wrong -- and reads `_entity`.
  `graphql_query` and `graphql_schema_get` returned a raw 404 whenever the site
  had no GraphQL server, which is the state a plain install leaves it in, since
  the module ships no default; they now say that, and name the config entity
  and the permission that fix it. `paragraphs_item_list` returned a bare 404
  for a bundle that does not exist, which reads as "paragraphs are missing"
  rather than "that type is not configured here"; it now lists the types the
  site does have
- Fix eleven hard-coded JSON:API filters that Drupal rejected outright, each
  returning an empty result on every call on every site. `commerce_product`,
  `commerce_promotion` and `commerce_shipping_method` filtered on `store` where
  the field is the plural `stores`, and `commerce_order` on `store` where it is
  the `store_id` reference; all four needed the `.id` specifier that entity
  references require. `webform_submission` filtered on `webform` where the field
  is `webform_id`, also a reference. `paragraphs_item_list` filtered on
  `paragraphs_type`, which is not a field at all -- a paragraph's type is its
  bundle, so it now addresses `paragraph--{type}`. `pathauto_pattern_list`
  filtered on `entity_type` and `bundle`, which live in a pattern's id as
  `{entity_type}--{bundle}`, so it now filters on `id` when it has both.
  `comments_thread_list` filtered on `pid` for top-level comments, but `pid` is
  a reference to the parent comment, so it 400'd -- and `pid.id = 0` would have
  returned nothing, since no comment has id 0; the whole thread is returned now,
  with each row's `pid` available for building the tree. `facets_facet_list`
  filtered on `index`, but a facet attaches to a facet source rather than to an
  index, so it lists facets and reports their `facet_source_id`
- Stop sending `langcode: "en"` in create payloads. Four tools did this. It is
  harmless on a single-language site, but once a second language exists the
  field is writable only with translation permission, so every create failed
  403 "the current user is not allowed to POST the selected field (langcode)" --
  including an ordinary authenticated user creating a term in the site's own
  language. The field is now sent only when the caller asks for a language
- Fix `drush_command` option rendering, which made every confirmation-answering
  call fail. Boolean options were emitted as `--key=value`, but drush flags take
  no value, so `options={"yes": True}` -- the documented way to install a module
  -- was rejected with "The --yes option does not accept a value" and nothing
  was installed while the tool reported success. A `False` was worse: it emitted
  the bare flag, so asking *not* to confirm silently suppressed confirmation on
  destructive commands. Zero-valued options were also mangled, `--count=0`
  becoming a bare `--count`. Booleans are now bare flags, `False` omits the
  option, and everything else keeps its value
- Return an `error` from `drush_command` when Drush exits non-zero. It handed
  back the raw result with no `error` key, so the generic escape hatch -- the
  tool an agent reaches for first -- still presented a failed command as an
  empty success, even though `ensure_dict` already fixed this for the 224
  specialised call sites
- Split several packages in `composer_require`. They arrived as one argv token,
  so composer read `drupal/pathauto` as a version constraint on `drupal/token`
  and refused the whole request with "Could not parse version constraint"
- Ask for `view`, not `views_view`: the entity type has been `view` since
  Drupal 8, so all six views tools 404'd on a site with Views installed and
  healthy, and read as "module not installed"
- Ask for `content_moderation_state`, not `moderation_state`, in the moderation
  tools. The node *field* is still called `moderation_state` and is unchanged
- Ask for `facets_facet`, not `search_api_facet`, in the facet tools
- Rewrite `config_translation_list` and `config_translation_add`, which targeted
  three mechanisms that do not exist between them: a `config_translation`
  JSON:API resource, a `config:translation:add` Drush command (Drush has no
  translation command category at all), and `$entity->addTranslation()` on a
  config entity, which implements no `TranslatableInterface`. The list reports
  the mappers this site has. The add resolves `{entity_type}/{entity_id}`
  through the config translation mapper to the config object the entity is
  stored as -- `node_type` and `article` become `node.type.article` -- and
  writes a language config override for the target language, which is where
  Drupal keeps config translations. Verified live: the French `name` and
  `description` land on the override while the base config keeps its own
- Drop a dead `get_resource("jsonapi")` call from `nextjs_helpers_generate`. It
  requested `/jsonapi/jsonapi`, a path that does not exist, and the 404 aborted
  the whole tool for a value the generator never used

- Implement the six `layout_builder_*` tools against the real API; they asked
  JSON:API for a resource that has never existed and returned an opaque 404 on
  every call, so reading, writing and reverting layouts now go through Drush to
  `entity_view_display` and `OverridesSectionStorage`
- Fix `DrushClient._flatten` shlex-splitting list arguments, which made
  `db_tables`, `db_query`, `db_count`, `drush_php_eval` and every `ev` tool fail
  with "Too many arguments"
- Report a failed Drush run as an `error`: `ensure_dict` passed
  `{returncode: 1, data: {}, stderr}` through untouched, byte for byte an empty
  success, so 224 call sites presented broken commands as empty results
- Return real tool schemas from `/mcp/tools/list`, which reported
  `input_schema: {}` for all 366 tools
- Fix `cron_list` (called Drupal 7's `drupal_get_cron_jobs()`, removed in
  Drupal 8), `queue_create` (a shell escape in PHP that never passes through a
  shell, so PHP died with a ParseError) and `queue_delete` (a second argument on
  all three paths when `queue:delete` accepts exactly one)
- Route `queue_create` and `queue_delete` around `drush queue:delete`, which
  resolves only registered queue services and answered "Queue not found" for a
  queue this server had just created
- Fix `permission_audit` and `menu_link_list` filtering on fields Drupal does
  not expose (`filter[name]` on `user_role`, `filter[menu]` on
  `menu_link_content`), a 400 on every call on every site
- Validate whole statements in `db_query`; a `SELECT 1; DROP TABLE x` passed the
  `startswith("SELECT")` guard and dropped the table
- Stop stacking log handlers on repeated `setup_logging` calls

### Removed

- Remove dead register_all_tools function from tools/__init__.py
- Remove duplicate _find_tool_path definition in security_audit.py

## [0.1.0] - 2026-10-13

### Added

- Initial release with 35+ MCP tools across all major Drupal categories
- FastMCP server with stdio and HTTP transports
- JSON:API and GraphQL clients with authentication
- Drush command execution via subprocess
- Multi-provider AI support (Ollama, OpenAI, Anthropic, NVIDIA NIM)
- Content management, user management, taxonomy, views, paragraphs tools
- DevOps tools for DDEV/Lando, Composer, database queries
- Migration tools for D7 to D10 upgrades
- Security audit and code quality tools
