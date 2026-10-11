# MCP Server + Coding Agent Integration Guide

## Overview

This document describes how to connect the Drupal MCP Server to a coding agent (Claude Desktop, Cursor, Continue, etc.) so the agent can perform all Drupal-related work through standardized tool calls.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Coding Agent (LLM)                           │
│  • Receives natural language requests                           │
│  • Discovers available tools via MCP                            │
│  • Plans and executes multi-step workflows                      │
└─────────────────────────┬───────────────────────────────────────┘
                          │ MCP Protocol (stdio)
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│              Drupal MCP Server (Python/FastMCP)                 │
│  • 38 tools across 6 modules                                    │
│  • 3 auth modes: Basic, OAuth2, Bearer Token                   │
│  • 3 clients: JSON:API, GraphQL, Drush                          │
│  • 4 AI providers: OpenAI, Anthropic, Ollama, Google           │
│  • DDEV/Lando local dev support                                 │
└─────────────────────────┬───────────────────────────────────────┘
                          │ HTTP/SSH
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Drupal Site(s)                               │
│  • Content management (nodes, users, taxonomy, media)          │
│  • Configuration (CMI, features, config split)                 │
│  • Migrations (Migrate API, Drush)                             │
│  • DevOps (cache, cron, updates, deployments)                  │
└─────────────────────────────────────────────────────────────────┘
```

## Agent Configuration

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "drupal": {
      "command": "python",
      "args": ["-m", "src.server"],
      "cwd": "/path/to/drupal-mcp-server",
      "env": {
        "DRUPAL_BASE_URL": "https://your-drupal-site.com",
        "DRUPAL_AUTH_MODE": "basic",
        "DRUPAL_USERNAME": "your-username",
        "DRUPAL_PASSWORD": "your-password"
      }
    }
  }
}
```

### Cursor

Add to `.cursor/mcp.json` in your project:

```json
{
  "mcpServers": {
    "drupal": {
      "command": "python",
      "args": ["-m", "src.server"],
      "cwd": "/path/to/drupal-mcp-server",
      "env": {
        "DRUPAL_BASE_URL": "https://your-drupal-site.com",
        "DRUPAL_AUTH_MODE": "basic",
        "DRUPAL_USERNAME": "your-username",
        "DRUPAL_PASSWORD": "your-password"
      }
    }
  }
}
```

### Continue (VS Code)

Add to `~/.continue/config.json`:

```json
{
  "mcpServers": {
    "drupal": {
      "command": "python",
      "args": ["-m", "src.server"],
      "cwd": "/path/to/drupal-mcp-server",
      "env": {
        "DRUPAL_BASE_URL": "https://your-drupal-site.com",
        "DRUPAL_AUTH_MODE": "basic",
        "DRUPAL_USERNAME": "your-username",
        "DRUPAL_PASSWORD": "your-password"
      }
    }
  }
}
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DRUPAL_BASE_URL` | Yes | - | Drupal site URL |
| `DRUPAL_AUTH_MODE` | No | `basic` | `basic`, `oauth`, `bearer` |
| `DRUPAL_USERNAME` | For basic | - | Drupal username |
| `DRUPAL_PASSWORD` | For basic | - | Drupal password |
| `DRUPAL_OAUTH_CLIENT_ID` | For oauth | - | OAuth client ID |
| `DRUPAL_OAUTH_CLIENT_SECRET` | For oauth | - | OAuth client secret |
| `DRUPAL_BEARER_TOKEN` | For bearer | - | Bearer token |
| `DRUPAL_GRAPHQL_ENDPOINT` | No | `/graphql` | GraphQL endpoint path |
| `DRUSH_ALIAS` | No | `@self` | Drush site alias |
| `AI_PROVIDER` | No | `openai` | `openai`, `anthropic`, `ollama`, `google` |
| `AI_API_KEY` | For cloud | - | API key for AI provider |
| `AI_MODEL` | No | Provider default | Model name |

## Available Tools by Module

### Content Tools (6)
| Tool | Status | Description |
|------|--------|-------------|
| `drupal_content_create` | ✅ Implemented | Create content (nodes, users, taxonomy terms) |
| `drupal_content_read` | ✅ Implemented | Read content by UUID or bundle |
| `drupal_content_update` | ✅ Implemented | Update existing content |
| `drupal_content_delete` | ✅ Implemented | Delete content |
| `drupal_content_list` | ✅ Implemented | List content with filters/pagination |
| `drupal_content_bulk_update` | 🔶 Stub | Bulk update multiple entities |
| `drupal_media_fix_issues` | 🔶 Stub | Fix common media issues |
| `drupal_alias_manage` | 🔶 Stub | Manage URL aliases |
| `drupal_content_quality_analyze` | 🔶 Stub | Analyze content quality |
| `drupal_test_content_generate` | 🔶 Stub | Generate test content |

### Migration Tools (7)
| Tool | Status | Description |
|------|--------|-------------|
| `drupal_migration_generate_yaml` | ✅ Implemented | Generate migration YAML |
| `drupal_migration_run_test` | ✅ Implemented | Run migration test |
| `drupal_migration_validate` | ✅ Implemented | Validate migration |
| `drupal_migration_rollback` | ✅ Implemented | Rollback migration |
| `drupal_migration_sync_media` | ✅ Implemented | Sync media files |
| `drupal_migration_module_config` | 🔶 Stub | Migrate module configuration |
| `drupal_migration_taxonomy` | 🔶 Stub | Migrate taxonomy |

### Config Tools (6)
| Tool | Status | Description |
|------|--------|-------------|
| `drupal_config_export` | ✅ Implemented | Export configuration |
| `drupal_config_import` | ✅ Implemented | Import configuration |
| `drupal_config_sync` | 🔶 Stub | Sync config between environments |
| `drupal_config_diff` | 🔶 Stub | Diff configurations |
| `drupal_config_split` | 🔶 Stub | Manage config split |

### Analysis Tools (5)
| Tool | Status | Description |
|------|--------|-------------|
| `drupal_analysis_inventory_content_types` | ✅ Implemented | Inventory content types |
| `drupal_analysis_inventory_modules` | ✅ Implemented | Inventory modules |
| `drupal_analysis_site_analyze` | 🔶 Stub | Full site analysis (D7/D9/D10) |
| `drupal_analysis_module_map` | 🔶 Stub | Map module equivalents |
| `drupal_analysis_deprecated_code` | 🔶 Stub | Detect deprecated code |

### DevOps Tools (7)
| Tool | Status | Description |
|------|--------|-------------|
| `drupal_devops_drush_command` | ✅ Implemented | Execute Drush command |
| `drupal_devops_ddev_start` | ✅ Implemented | Start DDEV |
| `drupal_devops_ddev_stop` | ✅ Implemented | Stop DDEV |
| `drupal_devops_ddev_exec` | ✅ Implemented | Execute in DDEV |
| `drupal_devops_lando_start` | ✅ Implemented | Start Lando |
| `drupal_devops_lando_stop` | ✅ Implemented | Stop Lando |
| `drupal_devops_acquia_deploy` | 🔶 Stub | Deploy to Acquia Cloud |
| `drupal_devops_backup_database` | 🔶 Stub | Backup/restore database |

### AI Tools (4)
| Tool | Status | Description |
|------|--------|-------------|
| `drupal_ai_complete` | ✅ Implemented | AI completion |
| `drupal_ai_analyze` | ✅ Implemented | AI analysis |
| `drupal_ai_generate` | ✅ Implemented | AI generation |
| `drupal_ai_migrate_assist` | ✅ Implemented | AI migration assistance |

## Example Agent Workflows

### Create a Blog Post with Featured Image
```text
User: "Create a blog post titled 'Drupal 11 Features' with a featured image from https://example.com/image.jpg"

Agent workflow:
1. drupal_content_create (node type: article, title: "Drupal 11 Features")
2. drupal_media_create (from URL, save as featured image)
3. drupal_content_update (attach media to node field_featured_image)
```

### Deploy Configuration from Dev to Prod
```text
User: "Deploy the configuration from dev to prod"

Agent workflow:
1. drupal_config_export (source: dev)
2. drupal_config_diff (dev vs prod)
3. drupal_config_import (target: prod, with validation)
```

### Migrate WordPress Site to Drupal
```text
User: "Migrate our WordPress site to Drupal 10"

Agent workflow:
1. drupal_analysis_site_analyze (WordPress source)
2. drupal_migration_generate_yaml (WordPress → Drupal mappings)
3. drupal_migration_validate
4. drupal_migration_run_test
4. drupal_migration_sync_media
```

### Security Update Workflow
```text
User: "Apply security updates to the site"

Agent workflow:
1. drupal_devops_drush_command (pm:security)
2. drupal_devops_drush_command (pm:update --security-only)
3. drupal_devops_drush_command (cr)
4. drupal_devops_drush_command (updatedb)
5. drupal_analysis_deprecated_code (check for breaking changes)
```

## Implementation Roadmap

### Phase 1: Implement Stub Tools (Highest Priority)
Target: ~80% real tool coverage
- [ ] 5 content stubs
- [ ] 2 migration stubs
- [ ] 3 config stubs
- [ ] 3 analysis stubs
- [ ] 2 devops stubs

### Phase 2: Composition Workflow Tools
Add 12+ high-level tools that combine basic operations:
- `create_blog_post_with_media`
- `migrate_wordpress_to_drupal`
- `deploy_config_dev_to_prod`
- `clear_and_warm_caches`
- `backup_full_site`
- `apply_security_updates`
- `translate_content_set`
- `generate_xml_sitemap`
- `setup_multilingual_site`
- `manage_media_library`
- `run_cron_maintenance`
- `create_content_view`

### Phase 3: Multi-Site Registry
- Single MCP server managing multiple Drupal sites
- Site switching via tool parameter
- Per-site configuration and credentials

### Phase 4: Governed Writes
- Write operation validation
- Approval workflows for production
- Dry-run mode for all mutating tools
- Audit logging

### Phase 5: Enhanced AI Integration
- Context-aware prompts with site schema
- Tool chaining for complex workflows
- Drupal-specific prompt templates

## Testing the Integration

1. Start the MCP server:
```bash
cd /path/to/drupal-mcp-server
python -m src.server
```

2. In your agent, ask: "List all content types on my Drupal site"

3. The agent should discover and call `drupal_analysis_inventory_content_types`

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Tools not discovered | Check MCP server starts without errors; verify stdio transport |
| Auth failures | Verify credentials in env; check Drupal user permissions |
| JSON:API 404 | Enable `jsonapi` module; check `DRUPAL_BASE_URL` |
| GraphQL errors | Enable `graphql` module; check `DRUPAL_GRAPHQL_ENDPOINT` |
| Drush not found | Install Drush in DDEV/Lando or use `drupal_devops_ddev_exec` |

## References

- [MCP Specification](https://modelcontextprotocol.io)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [Drupal JSON:API](https://www.drupal.org/project/jsonapi)
- [Drupal GraphQL](https://www.drupal.org/project/graphql)
- [Drush Commands](https://drushcommands.com)
