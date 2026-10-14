# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security

- Fix command injection vulnerabilities in code audit and security audit tools
- Fix SQL injection in database query tools
- Fix path traversal in media upload tool
- Add input validation for URLs, queue names, and file paths
- Add authentication check to /mcp/tools/list endpoint

### Added

- Add Lando support to SiteManager
- Add subprocess timeout to DrushClient
- Add OAuth token fetching to AuthManager
- Create shared tools/_utils.py with ensure_dict, validate_pagination, build_pagination_params
- Add pagination validation to list tools
- Add input validation to accessibility and performance tools
- Add LICENSE, CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md
- Add GitHub issue and PR templates

### Changed

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
  two mechanisms that do not exist: a `config_translation` JSON:API resource
  (Drupal stores config translations on the entity, not as entities) and a
  `config:translation:add` Drush command (Drush has no translation command
  category at all). The list now reports the config entity types this site can
  translate, and the add writes a real entity translation, naming
  `{entity_type}/{entity_id}` rather than a bare config name that cannot resolve
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
