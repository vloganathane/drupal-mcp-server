# Drupal MCP Server Examples

Practical examples demonstrating the **366 tools across 35 modules**.

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

### 2. Content Workflow (`content_workflow.py`)
Complete content creation workflow:
1. Create a node
2. Upload media
3. Set URL alias
4. Verify content

### 3. Migration Workflow (`migration_workflow.py`)
Complete D7→D10 migration workflow:
1. Analyze source site
2. Generate migration config
3. Create migration module
4. Test migration
5. Run full migration

### 4. Custom Tool (`custom_tool.py`)
Template for creating custom tool modules:
- How to structure a tool module
- Using shared utilities (`_utils.py`)
- Input validation patterns
- Error handling conventions

### 5. Environment Template (`.env.example`)
Configuration template covering:
- Drupal connection (JSON:API, auth)
- AI provider setup (Ollama, OpenAI, Anthropic, Google, NVIDIA NIM)
- Drush and DDEV paths
- Transport settings (stdio, HTTP, SSE)

## Tool Categories (35 modules, 366 tools)

| Category | Tools | Module |
|----------|-------|--------|
| Accessibility | 5 | `accessibility.py` |
| AI | 4 | `ai.py` |
| Analysis | 6 | `analysis.py` |
| Code Audit | 7 | `code_audit.py` |
| Comments | 10 | `comments.py` |
| Commerce | 18 | `commerce.py` |
| Config | 7 | `config.py` |
| Contact | 9 | `contact.py` |
| Content | 14 | `content.py` |
| Database | 4 | `database.py` |
| DevOps | 20 | `devops.py` |
| Drupal.org | 9 | `drupal_org.py` |
| Feeds | 12 | `feeds.py` |
| Fields | 10 | `fields.py` |
| Headless | 10 | `headless.py` |
| Layout Builder | 15 | `layout_builder.py` |
| Media Enhanced | 8 | `media_enhanced.py` |
| Menus | 10 | `menus.py` |
| Metatag | 9 | `metatag.py` |
| Migration | 7 | `migration.py` |
| Moderation | 12 | `moderation.py` |
| Module Development | 12 | `module_dev.py` |
| Multilingual | 18 | `multilingual.py` |
| Paragraphs | 10 | `paragraphs.py` |
| Pathauto | 9 | `pathauto.py` |
| Performance | 7 | `performance.py` |
| Redirects | 7 | `redirects.py` |
| Revisions | 5 | `revisions.py` |
| Scheduler | 7 | `scheduler.py` |
| Search API | 13 | `search_api.py` |
| Security Audit | 8 | `security_audit.py` |
| Taxonomy | 10 | `taxonomy.py` |
| Testing | 9 | `testing.py` |
| Theme Development | 11 | `theme_dev.py` |
| Users | 12 | `users.py` |
| Views | 7 | `views.py` |
| Webform | 16 | `webform.py` |

## Usage in Claude Desktop

Once configured, invoke tools naturally:

```
"Analyze my Drupal 7 site at https://old-site.com"
→ Uses analyze_d7_site tool

"Map these D7 modules to D10: views, ctools, webform"
→ Uses map_modules_d7_to_d10 tool

"Bulk update all article nodes to fix grammar"
→ Uses bulk_update_nodes tool

"Run drush cache:rebuild"
→ Uses drush_command tool

"Create a commerce store with products"
→ Uses commerce_store_create, commerce_product_create

"Generate Next.js helpers for JSON:API"
→ Uses nextjs_helpers_generate tool
```

## Next Steps

- Read [Architecture](docs/architecture.md) for system design
- Check [Migration Guide](docs/migration.md) for upgrade paths
- Browse tool modules in `src/drupal_mcp_server/tools/` for implementation details