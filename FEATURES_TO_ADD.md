# Features to Add — Updated Status

## Overview
The drupal-management-ai-agent provides a natural language interface for managing Drupal sites. Our MCP server now has **41 fully implemented tools** across 6 categories with no stubs remaining. This document tracks the next high-value tools to add.

---

## ✅ COMPLETED (All stubs resolved)

### Analysis (6/6) ✅
- `analyze_d7_site` — Real D7 analysis with 43 module mappings
- `analyze_d9_site` — Real D9 deprecated API scan (10 APIs)
- `inventory_content_types` — Real JSON:API call
- `inventory_modules` — Real Drush pm-list call
- `map_modules_d7_to_d10` — AI + 43 known mappings
- `find_deprecated_code` — Real filesystem scan

### Migration (7/7) ✅
- `generate_migration_yaml` — Real YAML generation
- `generate_module_migration` — Full module: source plugin + YAML + hooks
- `run_migration_test` — Real Drush migrate-import
- `validate_migration` — Real Drush migrate-status
- `rollback_migration` — Real Drush migrate-rollback
- `sync_media_files` — Real file sync
- `migrate_taxonomy` — Vocabularies + terms with hierarchy

### Content (7/7) ✅
- `clean_nodes_ai` — AI-powered with dry-run/confirm
- `map_fields_ai` — AI + JSON:API field discovery
- `bulk_update_nodes` — Real JSON:API bulk update
- `fix_media_references` — Real media reference scanning
- `bulk_update_aliases` — Real Drush uuri
- `analyze_content_quality` — AI analysis
- `generate_test_content` — Real JSON:API creation

### Config (5/5) ✅
- `export_config` — Real Drush config-export
- `import_config` — Real Drush config-import
- `sync_config` — Real env-to-env sync with dry-run
- `diff_config` — Real config-diff + YAML fallback
- `split_config` — Real config splitting from source dir

### DevOps (12/12) ✅
- `drush_command` — Any Drush command
- `ddev_setup/start/stop/exec` — Full DDEV lifecycle
- `lando_setup/start/stop/exec` — Full Lando lifecycle
- `acquia_deploy` — Dual-path: acquia-cli + legacy Drush
- `backup_database` — Real Drush sql-dump
- `cache_rebuild` — Real Drush cache-rebuild

### AI (4/4) ✅
- `ai_analyze_content_quality`
- `ai_suggest_field_mappings`
- `ai_generate_migration_plan`
- `ai_translate_content`

---

## 🎯 NEXT HIGH-PRIORITY TOOLS (25 tools, ~8 days)

### 1. Content CRUD (5 tools, 1-2 days)
| Tool | Description | Implementation |
|------|-------------|----------------|
| `create_node` | Create single node with fields | `jsonapi.create_resource("node--{bundle}", fields)` |
| `get_node` | Get node by ID with relationships | `jsonapi.get_by_id("node", nid)` |
| `update_node` | Update single node by ID | `jsonapi.update_resource("node", nid, fields)` |
| `delete_node` | Delete single node | `jsonapi.delete_resource("node", nid)` |
| `query_nodes` | Custom JSON:API query (filters, sorts, includes, pagination) | `jsonapi.get_resource("node--{bundle}", params)` |

### 2. Media Management (2 tools, 1 day)
| Tool | Description | Implementation |
|------|-------------|----------------|
| `upload_media` | Upload file to media library with alt text/metadata | Multipart POST to JSON:API media endpoint |
| `create_media` | Create media from URL or local file | `jsonapi.create_resource("media--{type}", data)` |

### 3. Taxonomy CRUD (3 tools, 1 day)
| Tool | Description | Implementation |
|------|-------------|----------------|
| `create_term` | Create taxonomy term in vocabulary | `jsonapi.create_resource("taxonomy_term--{vid}", data)` |
| `list_terms` | List terms in vocabulary with tree option | `jsonapi.get_resource("taxonomy_term--{vid}", params)` |
| `create_vocabulary` | Create taxonomy vocabulary | `jsonapi.create_resource("taxonomy_vocabulary", data)` |

### 4. Users CRUD (4 tools, 1 day)
| Tool | Description | Implementation |
|------|-------------|----------------|
| `create_user` | Create user account with roles | `jsonapi.create_resource("user--user", data)` |
| `get_user` | Get user by ID/email | `jsonapi.get_by_id("user--user", uid)` or filter |
| `list_users` | List users with filters | `jsonapi.get_resource("user--user", params)` |
| `assign_role` | Assign role to user | Drush `user:role:add` or JSON:API PATCH |

### 5. Config Get/Set (2 tools, 0.5 day)
| Tool | Description | Implementation |
|------|-------------|----------------|
| `config_get` | Get single config object by name | `jsonapi.get_resource("config", {"filter[name]": name})` |
| `config_set` | Set single config value | Drush `config:set` or JSON:API PATCH |

### 6. DevOps Essentials (5 tools, 1 day)
| Tool | Description | Implementation |
|------|-------------|----------------|
| `composer_install` | Run composer install | `drush.run("composer", ["install"])` or SiteManager |
| `composer_require` | Require package via composer | `drush.run("composer", ["require", package])` |
| `drush_cron` | Run cron | `drush.run("cron")` |
| `drush_watchdog` | Show recent log entries | `drush.run("watchdog:show", ["--count=50"])` |
| `cache_clear` | Clear specific cache bins | `drush.run("cache:rebuild")` or `drush.run("cache:clear", ["bin"])` |

### 7. Database Query (2 tools, 0.5 day)
| Tool | Description | Implementation |
|------|-------------|----------------|
| `db_query` | Run SELECT query via Drush | `drush.run("sql:query", [query])` |
| `db_tables` | List database tables | `drush.run("sql:query", ["SHOW TABLES"])` |

### 8. Site Building (2 tools, 1-2 days)
| Tool | Description | Implementation |
|------|-------------|----------------|
| `create_content_type` | Create content type with fields | Multiple JSON:API calls: node_type + field_config + field_storage_config |
| `add_field` | Add field to entity type | JSON:API field_config + field_storage_config creation |

---

## 📋 MEDIUM PRIORITY (Future)

### Search Integration
- `search_api_index` — Index content in Search API
- `search_api_clear` — Clear search index
- `search_execute` — Execute search query

### Workflows
- `workflow_list` — List workflows
- `workflow_transition` — Apply workflow transition

### Media Advanced
- `media_crop` — Crop image media
- `media_derivatives` — Generate image derivatives
- `media_replace` — Replace media file

### Performance
- `cache_clear` — Clear specific cache bins (partial)
- `redis_flush` — Flush Redis cache
- `varnish_purge` — Purge Varnish cache

### Multisite
- `site_list` — List multisite directories
- `site_create` — Create new multisite
- `site_alias` — Manage site aliases

---

## 🏗️ IMPLEMENTATION NOTES

### Pattern for New Tools
```python
@mcp.tool()
async def new_tool(param: type, ...) -> dict[str, Any]:
    """Description."""
    client = deps.get("client_name")
    if not client:
        return {"error": "Client not available"}
    try:
        result = await client.method(params)
        return result
    except Exception as e:
        return {"error": str(e)}
```

### Dependencies by Category
| Category | Primary Client | Secondary |
|----------|---------------|-----------|
| Content CRUD | JSON:API | AI (optional) |
| Media | JSON:API | Drush (file upload) |
| Taxonomy | JSON:API | - |
| Users | JSON:API | Drush (roles) |
| Config | JSON:API | Drush |
| DevOps | Drush | SiteManager |
| Database | Drush | - |
| Site Building | JSON:API | - |

### Testing Strategy
- Add unit tests for each new tool module
- Integration tests with real Drupal site (DDEV)
- Test dry-run/confirm patterns where applicable

---

## 📊 PROGRESS TRACKING

| Phase | Tools | Status | Target |
|-------|-------|--------|--------|
| Core (41) | 41 | ✅ Complete | Done |
| Content CRUD | 5 | 🔄 Next | Week 1 |
| Media | 2 | ⏳ Planned | Week 1 |
| Taxonomy | 3 | ⏳ Planned | Week 1 |
| Users | 4 | ⏳ Planned | Week 2 |
| Config Get/Set | 2 | ⏳ Planned | Week 2 |
| DevOps Essentials | 5 | ⏳ Planned | Week 2 |
| Database | 2 | ⏳ Planned | Week 2 |
| Site Building | 2 | ⏳ Planned | Week 3 |
| **Total** | **66** | | **~3 weeks** |

---

## 🎯 SUCCESS METRICS
- Tool count: 41 → 66 (+61%)
- Coverage: All common Drupal admin operations
- Unique advantages maintained: 13 tools no competitor has
- Zero stubs maintained
- mypy/ruff clean at each step
