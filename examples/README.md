# Drupal MCP Server Examples

Practical examples demonstrating the 35+ tools across all 6 categories.

## Quick Start

1. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your Drupal site details
   ```

2. **Install dependencies**:
   ```bash
   pip install -e .
   ```

3. **Run examples**:
   ```bash
   python examples/basic_usage.py
   ```

## Examples

### 1. Basic Usage (`basic_usage.py`)
Conceptual examples showing tool invocation patterns:
- Site analysis
- Content inventory
- AI-powered updates
- Drush commands
- DDEV workflow

### 2. Claude Desktop Config (`claude_desktop_config.json`)
Ready-to-use MCP server configuration for Claude Desktop:
- Copy to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
- Or `%APPDATA%/Claude/claude_desktop_config.json` (Windows)
- Restart Claude Desktop

### 3. Migration Workflow (`migration_workflow.md`)
Complete D7→D10 migration guide:
- Step-by-step tool usage
- AI-powered module mapping
- Content migration orchestration
- Post-migration cleanup

### 4. Environment Template (`.env.example`)
Configuration template covering:
- Drupal connection (JSON:API, auth)
- AI provider setup (Ollama, OpenAI, Anthropic, Google)
- Drush and DDEV paths

## Tool Categories

### Analysis (6 tools)
- `analyze_d7_site` / `analyze_d9_site`
- `inventory_content_types` / `inventory_modules`
- `map_modules_d7_to_d10`
- `find_deprecated_code`

### Migration (7 tools)
- `generate_migration_yaml`
- `run_migration_test` / `execute_migration`
- `validate_migration` / `rollback_migration`
- `check_migration_status` / `import_legacy_database`

### Content (7 tools)
- `bulk_update_nodes` / `bulk_update_nodes_ai`
- `clean_nodes_ai` / `deduplicate_content`
- `bulk_publish` / `bulk_unpublish`
- `generate_content_report`

### Config (5 tools)
- `export_config` / `import_config`
- `diff_config` / `sync_config`
- `validate_config`

### DevOps (6 tools)
- `drush_command`
- `ddev_start` / `ddev_stop` / `ddev_exec`
- `backup_database` / `restore_database`

### AI (4 tools)
- `ai_analyze_content_quality`
- `ai_suggest_tags`
- `ai_translate_content`
- `ai_generate_summary`

## Usage in Claude Desktop

Once configured, invoke tools naturally:

```
"Analyze my Drupal 7 site at https://old-site.com"
→ Uses analyze_d7_site tool

"Map these D7 modules to D10: views, ctools, webform"
→ Uses map_modules_d7_to_d10 tool

"Bulk update all article nodes to fix grammar"
→ Uses bulk_update_nodes_ai tool

"Run drush cache:rebuild"
→ Uses drush_command tool
```

## Next Steps

- Read [QUICKSTART.md](../docs/QUICKSTART.md) for setup
- Check [API.md](../docs/API.md) for full tool reference
- Review [architecture/overview.md](../docs/architecture/overview.md) for internals
