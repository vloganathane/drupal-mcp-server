# Drupal MCP Server

A Model Context Protocol (MCP) server for Drupal operations. Provides 35+ tools for site analysis, migration, content management, configuration, and DevOps operations.

## Features

- **JSON:API & GraphQL** - Full support for Drupal's REST endpoints
- **Drush Integration** - Execute any Drush command
- **DDEV/Lando Support** - Local development environment management
- **AI-Powered Tools** - Multi-provider AI (Ollama, OpenAI, Anthropic, NVIDIA NIM)
- **Migration Assistance** - Generate and validate migration configurations

## Installation

```bash
pip install drupal-mcp-server
```

Or with uv:

```bash
uv pip install -e .
```

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

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

## Usage

### As MCP Server (Claude Desktop)

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "drupal": {
      "command": "drupal-mcp"
    }
  }
}
```

### Direct Execution

```bash
drupal-mcp
```

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

### Content (7 tools)
- `clean_nodes_ai` - Clean duplicate nodes with AI
- `map_fields_ai` - AI field mapping suggestions
- `bulk_update_nodes` - Bulk node updates
- `fix_media_references` - Fix broken media refs
- `bulk_update_aliases` - Bulk URL alias updates
- `analyze_content_quality` - AI content analysis
- `generate_test_content` - Generate test content

### Config (5 tools)
- `export_config` - Export Drupal config
- `import_config` - Import Drupal config
- `sync_config` - Sync config between environments
- `diff_config` - Diff config between envs
- `split_config` - Split config for atomic deploy

### DevOps (6 tools)
- `drush_command` - Execute any Drush command
- `ddev_start` - Start DDEV project
- `ddev_stop` - Stop DDEV project
- `ddev_exec` - Execute in DDEV container
- `acquia_deploy` - Deploy to Acquia Cloud
- `backup_database` - Create database backup

### AI (4 tools)
- `ai_analyze_content_quality` - Analyze content quality
- `ai_suggest_field_mappings` - Suggest field mappings
- `ai_generate_migration_plan` - Generate migration plan
- `ai_translate_content` - Translate content

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
ruff check src/
```

## License

MIT
