# Drupal MCP Server

[![CI](https://github.com/vloganathane/drupal-mcp-server/actions/workflows/ci.yml/badge.svg)](https://github.com/vloganathane/drupal-mcp-server/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/vloganathane/drupal-mcp-server/branch/main/graph/badge.svg)](https://codecov.io/gh/vloganathane/drupal-mcp-server)
[![PyPI version](https://img.shields.io/pypi/v/drupal-mcp-server.svg)](https://pypi.org/project/drupal-mcp-server/)
[![Python versions](https://img.shields.io/pypi/pyversions/drupal-mcp-server.svg)](https://pypi.org/project/drupal-mcp-server/)
[![PyPI downloads](https://img.shields.io/pypi/dm/drupal-mcp-server.svg)](https://pypi.org/project/drupal-mcp-server/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/vloganathane/drupal-mcp-server/blob/main/LICENSE)

A Model Context Protocol (MCP) server for Drupal operations. Provides **414 tools across 41 modules** for site analysis, migration, content management, configuration, commerce, headless, DevOps, security, and more.

<img src="https://raw.githubusercontent.com/vloganathane/drupal-mcp-server/main/promo/thumbnail.png" alt="414 tools. One MCP server. — pip install drupal-mcp-server" width="100%">

## Demo

A real run — version check, the nine supported clients, live detection of the agents on this machine, and a zero-install start straight from PyPI:

<p align="center">
  <img src="https://raw.githubusercontent.com/vloganathane/drupal-mcp-server/main/promo/demo.gif" alt="Terminal demo: drupal-mcp --version, install --list, install --print, and uvx --from drupal-mcp-server drupal-mcp --version" width="860">
</p>

## Why Use This?

- **Unified interface** — Access JSON:API, GraphQL, Drush, and AI through one MCP server
- **AI-powered** — Content analysis, field mapping, and migration planning with your choice of LLM
- **Multi-transport** — Stdio for desktop apps, HTTP/SSE for remote deployments
- **Secure** — Input validation, OAuth 2.1, no shell injection
- **Comprehensive** — 37 tool modules covering every major Drupal subsystem

## Features

- **JSON:API & GraphQL** — Full support for Drupal's REST endpoints, schema introspection, sparse fieldsets
- **Drush Integration** — Execute any Drush command (cache, cron, updb, watchdog, php-eval, etc.)
- **DDEV/Lando/Acquia Support** — Local and cloud development environment management
- **AI-Powered Tools** — Multi-provider AI (Ollama, OpenAI, Anthropic, NVIDIA NIM, Google)
- **Migration Assistance** — Generate and validate migration configurations, D7→D10 upgrades
- **Security Audits** — PHPStan, Drupal Check, dependency scanning, SQL injection, XSS, CSP, file permissions
- **Content Management** — CRUD for nodes, media, users, taxonomy, comments, revisions, paragraphs
- **Commerce** — Stores, products, orders, payments, promotions, shipping (18 tools)
- **Configuration** — Export/import, sync, diff, split (7 tools)
- **DevOps** — Database queries, Composer, cache, cron, queues, backups (20 tools)
- **Headless** — Next.js/Gatsby helpers, JSON:API optimization, GraphQL schema (10 tools)
- **Search** — Search API servers, indexes, facets, reindex (13 tools)
- **Multilingual** — Languages, content translation, interface translation, config translation (18 tools)
- **Module Development** — Scaffolding for modules, services, plugins, forms, controllers, tests (12 tools)
- **Theme Development** — Theme creation, libraries, regions, templates, preprocessing, assets (11 tools)
- **Webform** — Forms, submissions, elements, handlers, tokens, export (16 tools)

## Installation

```bash
pip install drupal-mcp-server
```

Or with uv:

```bash
uv pip install drupal-mcp-server
```

## Quickstart

### 1. Configure

```bash
cp examples/.env.example .env
```

Minimal `.env`:

```bash
DRUPAL_BASE_URL=https://your-drupal-site.com
DRUPAL_USERNAME=admin
DRUPAL_PASSWORD=secret
```

### 2. Run

```bash
drupal-mcp
```

### 3. Use with Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "drupal": {
      "command": "drupal-mcp",
      "env": {
        "DRUPAL_BASE_URL": "https://your-drupal-site.com",
        "DRUPAL_USERNAME": "admin",
        "DRUPAL_PASSWORD": "secret"
      }
    }
  }
}
```

## AI Coding Agents

Register the server with any MCP client in one command:

```bash
drupal-mcp install
```

It detects the agents on your machine — Claude Code, Claude Desktop, Cursor,
Codex CLI, OpenCode, Windsurf, Pi, Hermes Agent and OpenClaw — gathers
`DRUPAL_*` settings from `./.env` or the environment, and writes each client's
config (preferring the client's own `mcp add` command when it has one).

```bash
drupal-mcp install --client claude-code --print   # preview without writing
drupal-mcp install --command 'uvx --from drupal-mcp-server drupal-mcp'  # run from PyPI, no install
```

See the [AI Coding Agents guide](docs/agents.md) for per-client copy-paste
snippets, options, and caveats.

## Configuration

### Drupal connection

| Variable | Default | Description |
|----------|---------|-------------|
| `DRUPAL_BASE_URL` | `http://localhost` | Base URL of the Drupal site |
| `DRUPAL_USERNAME` / `DRUPAL_PASSWORD` | — | Credentials (see below) |
| `DRUPAL_VERIFY_SSL` | `true` | Set `false` for self-signed dev certs (DDEV, Lando) |

### Authentication

Set `DRUPAL_USERNAME` and `DRUPAL_PASSWORD`. Drupal rejects basic auth on its
write endpoints with 403, so the server logs in to `/user/login`, reuses the
session cookie, and attaches the CSRF token that mutating JSON:API requests
require. Basic auth headers are still sent when a session cannot be
established, so reads keep working on sites without `/user/login`.

Other methods, used when the username/password pair is not set:

1. **OAuth2** — Set `DRUPAL_OAUTH_CLIENT_ID`, `DRUPAL_OAUTH_CLIENT_SECRET`, `DRUPAL_OAUTH_TOKEN_URL`
2. **Bearer Token** — Set `DRUPAL_API_TOKEN`, sent as `Authorization: Bearer`

### Drush

Drush tools shell out to `DRUSH_PATH` (default `drush`). It may contain
arguments, so container-based setups work:

```bash
DRUSH_PATH="ddev drush"    # start the MCP server from the project directory
```

### AI Providers

Set `DEFAULT_AI_PROVIDER` to one of:

- `ollama` (default, local)
- `openai`
- `anthropic`
- `nvidia_nim`
- `google`

### Transport

Set `MCP_TRANSPORT` to one of:

- `stdio` (default, for desktop apps)
- `http` (for remote HTTP deployment)
- `sse` (for Server-Sent Events)
- `streamable-http` (for Streamable HTTP)

HTTP transports serve tools that execute drush, composer and shell commands,
so the server refuses to bind one unless `DRUPAL_OAUTH_CLIENT_ID` is set —
MCP-side tokens are then issued and checked in-process; set
`MCP_ALLOW_INSECURE_HTTP=1` to serve unauthenticated on the default
loopback `MCP_HOST` (`127.0.0.1`) if you accept the risk. See
[Configuration](configuration.md#serving-over-http). Once bound,
`MCP_READ_ONLY=1` hides every tool that writes (185 of 414 remain — no
drush, composer, shell, or file output) and `MCP_RATE_LIMIT` caps
requests per client with `429` + `Retry-After`.

## Tools (414 total)

### Accessibility (5)
- `accessibility_axe_scan` — Run axe-core accessibility scan
- `accessibility_wcag_check` — WCAG compliance check
- `accessibility_color_contrast` — Color contrast validation
- `accessibility_aria_validate` — ARIA attribute validation
- `accessibility_report_generate` — Generate accessibility report

### AI (4)
- `ai_analyze_content_quality` — Analyze content quality with AI
- `ai_suggest_field_mappings` — Suggest field mappings between bundles
- `ai_generate_migration_plan` — Generate migration plan with AI
- `ai_translate_content` — Translate content with AI

### Analysis (9)
- `analyze_d7_site` — Analyze D7 site for D10 readiness
- `analyze_d9_site` — Analyze D9+ for deprecated APIs
- `inventory_content_types` — List all content types
- `inventory_modules` — List all modules
- `map_modules_d7_to_d10` — AI-powered module mapping D7→D10
- `find_deprecated_code` — Scan for deprecated APIs
- `find_entity_references` — Bundles whose reference fields target an entity type
- `search_entities` — Substring search across titles, names, and subjects
- `find_entity_by_path` — Resolve a URL path or alias to its entity

### Code Audit (7)
- `code_audit_phpstan` — Run PHPStan static analysis
- `drupal_check` — Run Drupal Check
- `code_sniffer` — Run PHP_CodeSniffer
- `deprecation_scan` — Scan for deprecated code
- `security_audit` — Security-focused code audit
- `composer_audit` — Composer dependency audit
- `code_quality_report` — Combined code quality report

### Codebase (12)
- `codebase_index_refresh`, `codebase_search`, `codebase_module_list`, `codebase_module_describe`
- `codebase_unused_modules`, `codebase_redundancy_check`, `codebase_hooks_find`, `codebase_paths_list`
- `codebase_files_list`, `codebase_directory_tree`, `codebase_file_read`, `codebase_function_read`

### Comments (10)
- `comment_list`, `comment_get`, `comment_create`, `comment_update`, `comment_delete`
- `comment_thread_list`, `comment_approve`, `comment_unapprove`
- `comment_field_settings`, `comment_field_configure`

### Commerce (18)
- `commerce_store_list`, `commerce_store_get`, `commerce_store_create`, `commerce_store_update`
- `commerce_product_list`, `commerce_product_get`, `commerce_product_create`, `commerce_product_update`
- `commerce_order_list`, `commerce_order_get`, `commerce_order_create`, `commerce_order_update`
- `commerce_payment_gateway_list`, `commerce_payment_gateway_get`
- `commerce_promotion_list`, `commerce_promotion_create`
- `commerce_shipping_method_list`, `commerce_shipping_method_create`

### Config (8)
- `config_get`, `config_set`, `export_config`, `import_config`, `sync_config`, `diff_config`, `split_config`, `config_status`

### Contact (9)
- `contact_form_list`, `contact_form_get`, `contact_form_create`, `contact_form_update`, `contact_form_delete`
- `contact_message_list`, `contact_message_get`, `contact_message_delete`, `contact_spam_check`

### Content (14)
- `create_node`, `get_node`, `update_node`, `delete_node`, `query_nodes`
- `upload_media`, `create_media`
- `clean_nodes_ai`, `map_fields_ai`, `bulk_update_nodes`
- `fix_media_references`, `bulk_update_aliases`
- `analyze_content_quality`, `generate_test_content`

### Database (4)
- `db_query`, `db_tables`, `db_table_info`, `db_count`

### DevOps (20)
- `drush_command` — Execute any Drush command
- `ddev_setup`, `ddev_start`, `ddev_stop`, `ddev_exec`
- `lando_start`, `lando_stop`, `lando_exec`, `lando_setup`
- `acquia_deploy`, `backup_database`, `cache_rebuild`
- `composer_install`, `composer_require`, `composer_update`
- `drush_cron`, `drush_watchdog`, `cache_clear`, `drush_updb`, `drush_php_eval`

### Drupal.org (12)
- `module_search`, `module_get`, `module_versions`, `module_dependencies`, `module_compatibility`
- `theme_search`, `theme_get`, `release_history`, `project_usage`
- `module_issues_search`, `module_popular`, `module_recommendation`

### Exports (4)
- `export_nodes`, `export_users`, `export_media`, `export_taxonomy`

### Feeds (12)
- `feeds_feed_list`, `feeds_feed_get`, `feeds_feed_create`, `feeds_feed_update`, `feeds_feed_delete`
- `feeds_import`, `feeds_import_status`, `feeds_log_list`
- `feeds_tamper_list`, `feeds_parser_list`, `feeds_fetcher_list`, `feeds_processor_list`

### Fields (10)
- `field_config_list`, `field_config_get`, `field_config_create`, `field_config_update`, `field_config_delete`
- `field_storage_list`, `field_storage_get`, `field_storage_create`, `field_storage_update`, `field_storage_delete`

### Headless (10)
- `jsonapi_schema_get`, `jsonapi_include_optimize`, `jsonapi_sparse_fieldsets`, `jsonapi_resources_list`, `jsonapi_resource_types`
- `graphql_schema_get`, `graphql_query`, `graphql_schema_extend`
- `nextjs_helpers_generate`, `gatsby_helpers_generate`

### Layout Builder (15)
- `block_list`, `block_get`, `block_create`, `block_update`, `block_delete`, `block_place`
- `layout_builder_list`, `layout_builder_get`, `layout_builder_create`, `layout_builder_update`
- `layout_builder_sections_list`, `layout_builder_section_add`
- `block_plugin_list`, `block_region_list`, `layout_builder_override_remove`

The `block_*` tools work normally. Layout Builder has no JSON:API resource, so
the `layout_builder_*` tools go through Drush to the real API instead:
`entity_view_display` holds the sections, and per-entity overrides live in the
entity's `layout_builder__layout` field. `layout_builder_list` reports which
displays have Layout Builder enabled; `layout_builder_get`,
`layout_builder_sections_list`, `layout_builder_section_add`,
`layout_builder_create` and `layout_builder_update` read and write the layout;
`layout_builder_override_remove` reverts an entity's override.

### Media Enhanced (8)
- `media_type_list`, `media_type_get`, `media_type_create`
- `media_create_from_url`, `media_create_from_base64`, `media_derivative_generate`
- `media_bulk_import`, `media_library_list`

### Menus (10)
- `menu_list`, `menu_get`, `menu_create`, `menu_update`, `menu_delete`
- `menu_link_list`, `menu_link_get`, `menu_link_create`, `menu_link_update`, `menu_link_delete`

### Metatag (9)
- `metatag_config_list`, `metatag_config_get`, `metatag_config_create`, `metatag_config_update`
- `metatag_defaults_get`, `metatag_defaults_set`, `metatag_token_list`
- `metatag_canonical_set`, `metatag_jsonld_generate`

### Migration (17)
- `generate_migration_yaml` — Generate migration YAML
- `generate_module_migration` — Generate migration module
- `run_migration_test` — Test migration with limited records
- `validate_migration` — Validate migration config
- `rollback_migration` — Rollback a migration
- `sync_media_files` — Sync media between paths
- `migrate_taxonomy` — Migrate taxonomy vocabularies
- `create_migration_plan` — Create a persisted migration manifest
- `get_migration_plan` — Read a migration manifest and tracked state
- `list_migration_plans` — List migration manifests
- `migration_status` — Summarize migration progress
- `migrate_records` — Copy a batch of source records to the target site
- `record_migration_result` — Record externally executed migration outcomes
- `analyze_source_site` — Analyze a source Drupal JSON:API resource type
- `reconcile_migration_counts` — Compare source and target counts
- `run_migration_wave` — Fetch and migrate one source resource type
- `run_migration` — Run an ordered end-to-end migration for all planned types

### Moderation (13)
- `moderation_state_list`, `moderation_state_get`, `moderation_state_create`, `moderation_state_update`, `moderation_state_delete`
- `moderation_transition_list`, `moderation_transition_get`, `moderation_transition_create`, `moderation_transition_execute`, `moderation_transition_delete`
- `content_moderation_dashboard`, `workflow_list`, `workflow_get`

### Module Development (12)
- `module_create`, `module_service_create`, `module_plugin_create`, `module_form_create`
- `module_controller_create`, `module_event_subscriber_create`, `module_hook_implement`
- `module_info_generate`, `module_permission_create`, `module_config_schema_create`
- `module_test_create`, `module_dependencies_analyze`

### Multilingual (18)
- `language_list`, `language_get`, `language_add`, `language_enable`, `language_disable`, `language_delete`
- `content_translation_enable`, `translation_status`, `translation_add`, `translation_update`
- `interface_translation_list`, `interface_translation_add`, `interface_translation_update`, `interface_translation_delete`
- `config_translation_list`, `config_translation_add`
- `language_negotiation_get`, `language_negotiation_set`

### Paragraphs (10)
- `paragraphs_type_list`, `paragraphs_type_get`, `paragraphs_type_create`, `paragraphs_type_update`, `paragraphs_type_delete`
- `paragraphs_item_list`, `paragraphs_item_get`, `paragraphs_item_create`, `paragraphs_item_update`, `paragraphs_item_delete`

### Pathauto (8)
- `pathauto_pattern_list`, `pathauto_pattern_get`, `pathauto_pattern_create`, `pathauto_pattern_update`, `pathauto_pattern_delete`
- `pathauto_generate`, `pathauto_token_list`, `redirect_pattern_list`

### Performance (7)
- `performance_query_log`, `performance_cache_stats`, `performance_redis_info`
- `performance_bigpipe_status`, `performance_bigpipe_enable`, `performance_memcached_stats`
- `performance_page_load_analyze`

### Redirects (7)
- `redirect_list`, `redirect_get`, `redirect_create`, `redirect_update`, `redirect_delete`
- `redirect_bulk_create`, `redirect_bulk_delete`

### Revisions (5)
- `revision_list`, `revision_get`, `revision_revert`, `revision_delete`, `revision_diff`

### Scheduler (7)
- `cron_run`, `cron_list`, `queue_list`, `queue_run`, `queue_delete`, `queue_info`, `queue_create`

### Search API (13)
- `search_api_server_list`, `search_api_server_get`, `search_api_server_create`, `search_api_server_enable`, `search_api_server_disable`
- `search_api_index_list`, `search_api_index_get`, `search_api_index_create`, `search_api_index_update`
- `search_api_index_reindex`, `search_api_index_clear`, `search_api_facet_list`, `search_api_facet_create`

### Security Audit (10)
- `security_scan` — PHPStan with security extensions
- `dependency_scan` — Composer audit
- `config_security_check` — Drupal config security
- `permission_audit` — Role and permission audit
- `sql_injection_scan` — SQL injection detection
- `xss_scan` — XSS vulnerability detection
- `csp_audit` — Content Security Policy audit
- `file_permissions_audit` — File permissions audit
- `code_security_scan` — Local pattern scan, nothing to install
- `route_access_audit` — Route access control classification

### Status (4)
- `status_report` — The site's status report (/admin/reports/status), read-only
- `database_updates` — Pending database updates, read-only
- `available_updates` — Packages with newer versions, from composer
- `health_check` — Drush, database, JSON:API, and module diagnostics

### Taxonomy (10)
- `create_vocabulary`, `get_vocabulary`, `update_vocabulary`, `delete_vocabulary`, `list_vocabularies`
- `create_term`, `get_term`, `update_term`, `delete_term`, `list_terms`

### Testing (9)
- `test_run_phpunit`, `test_run_kernel`, `test_run_behat`, `test_run_nightwatch`
- `test_scaffold_phpunit`, `test_scaffold_behat`, `test_scaffold_nightwatch`
- `test_coverage_report`, `test_list_suites`

### Theme Analysis (8)
- `theme_active`, `theme_info`, `theme_regions`, `theme_blocks`
- `theme_templates`, `theme_template_overrides`, `template_suggestions`
- `view_template_info`

### Theme Development (11)
- `theme_create`, `theme_library_create`, `theme_region_create`, `theme_template_override`
- `theme_preprocess_function`, `theme_breakpoint_create`, `theme_base_change`
- `theme_settings_form`, `theme_asset_optimize`, `theme_debug_enable`, `theme_lint_twig`

### Users (12)
- `create_user`, `get_user`, `get_user_by_email`, `update_user`, `delete_user`, `list_users`
- `assign_role`, `remove_role`, `list_roles`, `get_user_roles`, `block_user`, `unblock_user`

### Views (7)
- `views_list`, `views_get`, `views_create`, `views_update`, `views_delete`, `views_execute`, `views_export`

### Webform (16)
- `webform_list`, `webform_get`, `webform_create`, `webform_update`, `webform_delete`
- `webform_submission_list`, `webform_submission_get`, `webform_submission_delete`
- `webform_element_list`, `webform_element_create`
- `webform_handler_list`, `webform_handler_create`, `webform_handler_update`, `webform_handler_delete`
- `webform_token_list`, `webform_export_submissions`

## Documentation

- [Contributing Guide](docs/CONTRIBUTING.md)
- [Changelog](docs/CHANGELOG.md)
- [Security Policy](docs/SECURITY.md)
- [Code of Conduct](docs/CODE_OF_CONDUCT.md)
- [Architecture](docs/architecture.md)
- [Migration Guide](docs/migration.md)
- [Docstring Standard](docs/docstring_standard.md)

## Known limitations

These are real constraints of Drupal and its APIs, not TODOs. Each was confirmed
against a live Drupal 11 site under DDEV, and the affected tools say so at runtime
rather than returning an opaque error.

- **Layout Builder has no JSON:API resource.** The six `layout_builder_*` tools
  originally asked JSON:API for a resource that has never existed and returned an
  opaque 404. They now go through Drush to the real API — sections are the
  `layout_builder.sections` third-party setting on `entity_view_display`, and
  per-entity overrides live in the entity's `layout_builder__layout` field — so
  reading, writing and reverting layouts all work. The API has no display-level
  lock, so the `lock` argument marks components rather than the display.
- **Revisions have no collection endpoint.** JSON:API addresses a single revision via
  `?resourceVersion=id:<vid>` but exposes no revision listing or deletion, so
  `revision_list` and `revision_delete` return an honest limitation error rather than
  a 404.
- **Drush offers no per-run queue limit.** `queue:run` drains the whole queue and has
  neither `--limit` nor `--count`. `queue_run` runs without one and reports that the
  requested limit could not be applied.
- **Drush only knows registered queues.** `queue:list` and `queue:run` resolve queue
  *workers* that a module registered as a service, so `queue_list` and `queue_info`
  cannot see a queue nothing has registered, and `queue_run` answers "Queue not found"
  for one — including a queue `queue_create` just made. `queue_create` and
  `queue_delete` deliberately go around this and work on any queue name.
- **Composer is its own binary.** Drush ships no `composer` command, so
  `composer_install` / `composer_require` / `composer_update` / `composer_audit` run
  `composer` directly and need it on `PATH` (or at `./vendor/bin/composer`). They
  also do not require Drush. When the project is a DDEV or Lando project the
  command runs as `ddev composer` / `lando composer` instead: the host binary
  resolves against the host's PHP, which once locked in a `doctrine/collections`
  release needing 8.4 for a container running 8.3 — Composer's platform check
  then aborted every subsequent request and took the site down.
- **GraphQL needs a server before `/graphql` exists.** The module installs no
  default, so `graphql_query` and `graphql_schema_get` answer a bare 404 on a
  fresh site. They now explain that, naming the `graphql_server` config entity,
  the `execute default arbitrary graphql requests` permission, and the fact that
  `basic_auth` has to be enabled before credentials reach Drupal at all.
- **`langcode` is not always writable.** With `content_translation` installed
  and no bundle configured for translation, JSON:API refuses any write to
  `langcode` with a 403 regardless of the value sent — `"en"` as much as a
  nonsense one. The create tools omit it unless a language was asked for, so a
  create succeeds; one that does pass it gets Drupal's own explanation.
- **Security scanning needs PHPStan 1.x.** Older PHPStan has no `--exclude-path`; the
  tools probe for it and fall back rather than failing.
- **`release_history` for Drupal 7 projects.** packages.drupal.org is the live source
  for releases, dependencies, and core compatibility. D7-era projects fall back to
  updates.drupal.org's XML feed, which has been frozen since Drupal 8.
- **DDEV's key is `docroot`, not `webroot`.** DDEV 1.24 silently drops an
  unrecognised key, so `ddev_setup` writes `docroot:` — an empty docroot makes nginx
  serve the project root and every request 404s.

Modules the tools target are installed in the test site — Commerce, Paragraphs,
Webform, Search API, Feeds, Metatag, Pathauto — so a missing module is no longer
the usual explanation for a tool that does nothing. Two resources stay out of
reach by design: `content_moderation_state` is never exposed through JSON:API,
and `feeds_feed` needs a feed type with a `feeds_item` field configured on its
target bundle. Both are reported as not exposed rather than as failures.

## Development

```bash
# Create venv
python3 -m venv venv
source venv/bin/activate

# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/ tests/

# Type check
mypy src/drupal_mcp_server/
```

The offline suite cannot catch most of the bugs that matter in this package —
they need a real Drupal. Live runs do, and `tests/live/README.md` lists what
each one has found so far:

```bash
python tests/live/smoke_test.py           # 9 end-to-end cases, ~30s
python tests/live/layout_builder_test.py  # 10 Layout Builder cases, ~60s
python tests/live/queue_test.py           # 18 cron/queue cases, ~60s
python tests/live/filter_check.py         # every hard-coded JSON:API filter
python tests/live/resource_check.py       # every resource name, asked of Drupal
python tests/live/install_modules.py      # the modules the tools assume, ~10 min
python tests/live/sweep.py                # all 414 tools, ~30 min
python tests/live/mcp_call.py list_vocabularies '{}'  # one call, for spot checks
```

They need `ddev` running and the site in `drupal-live/`; `tests/live/README.md`
covers setup.

## License

MIT