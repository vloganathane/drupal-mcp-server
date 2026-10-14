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
