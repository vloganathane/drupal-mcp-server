# Drupal MCP Server

[![CI](https://github.com/drupal-mcp/drupal-mcp-server/actions/workflows/ci.yml/badge.svg)](https://github.com/drupal-mcp/drupal-mcp-server/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/drupal-mcp/drupal-mcp-server/branch/main/graph/badge.svg)](https://codecov.io/gh/drupal-mcp/drupal-mcp-server)
[![PyPI version](https://badge.fury.io/py/drupal-mcp-server.svg)](https://badge.fury.io/py/drupal-mcp-server)
[![Python versions](https://img.shields.io/pypi/pyversions/drupal-mcp-server.svg)](https://pypi.org/project/drupal-mcp-server/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/drupal-mcp/drupal-mcp-server/blob/main/LICENSE)

A Model Context Protocol (MCP) server for Drupal operations. Provides 35+ tools for site analysis, migration, content management, configuration, and DevOps operations.

## Why Use This?

- **Unified interface** — Access JSON:API, GraphQL, Drush, and AI through one MCP server
- **AI-powered** — Content analysis, field mapping, and migration planning with your choice of LLM
- **Multi-transport** — Stdio for desktop apps, HTTP/SSE for remote deployments
- **Secure** — Input validation, OAuth 2.1, no shell injection

## Features

- **JSON:API & GraphQL** - Full support for Drupal's REST endpoints
- **Drush Integration** - Execute any Drush command
- **DDEV/Lando Support** - Local development environment management
- **AI-Powered Tools** - Multi-provider AI (Ollama, OpenAI, Anthropic, NVIDIA NIM)
- **Migration Assistance** - Generate and validate migration configurations
- **Security Audits** - PHPStan, Drupal Check, dependency scanning
- **Content Management** - CRUD for nodes, media, users, taxonomy, comments
- **DevOps** - Config export/import, database queries, cron, queues

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

## Configuration

### Authentication

The server supports three auth methods (in priority order):

1. **Basic Auth** - Set `DRUPAL_USERNAME` and `DRUPAL_PASSWORD`
2. **OAuth2** - Set `DRUPAL_OAUTH_CLIENT_ID`, `DRUPAL_OAUTH_CLIENT_SECRET`, `DRUPAL_OAUTH_TOKEN_URL`
3. **Bearer Token** - Set via `DRUPAL_API_TOKEN`

### AI Providers

Set `DEFAULT_AI_PROVIDER` to one of:
- `ollama` (default, local)
- `openai`
- `anthropic`
- `nvidia_nim`

### Transport

Set `MCP_TRANSPORT` to one of:
- `stdio` (default, for desktop apps)
- `http` (for remote HTTP deployment)
- `sse` (for Server-Sent Events)
- `streamable-http` (for Streamable HTTP)

## Tools

### Analysis (6 tools)
- `analyze_d7_site` - Analyze D7 site for D10 readiness
- `analyze_d9_site` - Analyze D9+ for deprecated APIs
- `inventory_content_types` - List all content types
- `inventory_modules` - List all modules
- `map_modules_d7_to_d10` - AI-powered module mapping
- `find_deprecated_code` - Scan for deprecated APIs

### Migration (7 tools)
- `generate_migration_yaml` - Generate migration YAML
- `generate_module_migration` - Generate migration module
- `run_migration_test` - Test migration with limited records
- `validate_migration` - Validate migration config
- `rollback_migration` - Rollback a migration
- `sync_media_files` - Sync media between paths
- `migrate_taxonomy` - Migrate taxonomy vocabularies

### Content (12 tools)
- `create_node` / `get_node` / `update_node` / `delete_node` / `query_nodes`
- `upload_media` / `create_media`
- `clean_nodes_ai` - Clean duplicate nodes with AI
- `map_fields_ai` - AI field mapping suggestions
- `bulk_update_nodes` - Bulk node updates
- `analyze_content_quality` - AI content analysis
- `generate_test_content` - Generate test content

### Users (8 tools)
- `create_user` / `get_user` / `update_user` / `delete_user` / `list_users`
- `assign_role` / `remove_role` / `block_user` / `unblock_user`

### Taxonomy (7 tools)
- CRUD for vocabularies and terms
- `list_terms` with filtering and pagination

### DevOps (10 tools)
- `drush_command` - Execute any Drush command
- `ddev_start` / `ddev_stop` / `ddev_exec`
- `lando_start` / `lando_stop` / `lando_exec`
- `backup_database` / `cache_rebuild` / `drush_cron`

### Security Audit (6 tools)
- `security_scan` - PHPStan with security extensions
- `dependency_scan` - Composer audit
- `permission_audit` - Role and permission audit
- `sql_injection_scan` - SQL injection detection
- `xss_scan` - XSS vulnerability detection
- `config_security_check` - Drupal config security

### Module Development (10 tools)
- `module_create` - Full module scaffolding
- `module_service_create` - Service class generation
- `module_plugin_create` - Plugin scaffolding
- `module_form_create` - Form class generation
- `module_controller_create` - Controller with routing
- `module_event_subscriber_create` - Event subscriber
- `module_hook_implement` - Hook implementation
- `module_test_create` - PHPUnit test scaffolding

## Documentation

- [Contributing Guide](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)
- [Security Policy](SECURITY.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)

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

## License

MIT
