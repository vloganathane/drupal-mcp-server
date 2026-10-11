# Features to Add from drupal-management-ai-agent

## Overview
The drupal-management-ai-agent provides a natural language interface for managing Drupal sites. While our MCP server focuses on exposing granular tools for AI agent consumption, we can enhance our implementation by adding higher-level composition tools and improving existing stubs.

## Recommended Features to Add

### 1. Content Management Tools (Replace Stubs)
Replace content module stubs with real implementations:
- **bulk_update_nodes** - Update multiple nodes matching criteria
- **fix_media_references** - Fix broken media file references
- **analyze_content_quality** - Analyze content for readability, SEO, accessibility
- **generate_test_content** - Generate test content for development/staging
- **clean_nodes_ai** - Delete/cleanup nodes using AI criteria
- **map_fields_ai** - Map fields between content types/entities

### 2. Analysis Tool Enhancements
Replace analysis module stubs:
- **analyze_d7_site** - Actual Drupal 7 site analysis (modules, themes, customs)
- **analyze_d9_site** - Actual Drupal 9 site analysis (deprecated code, Symfony usage)
- **map_modules_d7_to_d10** - Map Drupal 7 modules to Drupal 10 equivalents

### 3. Migration Tool Enhancements
Replace migration module stubs:
- **generate_module_migration** - Generate migration YAML for custom modules
- **migrate_taxonomy** - Migrate taxonomy terms/vocabularies between sites

### 4. Config Tool Enhancements
Replace config module stubs:
- **sync_config** - Synchronize configuration between environments
- **diff_config** - Show configuration differences (YAML diff)
- **split_config** - Split config into modules/features for modular deployment

### 5. DevOps Tool Enhancement
- **acquia_deploy** - Actual deployment to Acquia Cloud (site preparation, code push, DB update)

### 6. Higher-Level Composition Tools
Add new tools for common workflows:
- **create_content** - Create node/content (title, body, type, fields via JSON:API)
- **update_content** - Update existing node by ID
- **upload_media** - Upload file to media library with alt text/metadata
- **query_content** - Execute custom JSON:API/GraphQL query
- **clear_cache** - Clear Drupal cache (drush cr)
- **rebuild_cache** - Rebuild cache (drush cr)
- **run_cron** - Execute cron (drush cron)
- **enable_module** - Enable module (drush en <module>)
- **disable_module** - Disable module (drush dis <module>)
- **update_database** - Apply database updates (drush updb)
- **create_site** - Create new Drupal site with DDEV/Lando (scaffold, install, configure)

## Implementation Approach
1. **Priority**: Replace stubs with real implementations first (provides immediate value)
2. **Secondary**: Add composition tools for common workflows

## Benefit
- Increases percentage of real tools from ~50% to ~80%+
- Provides more complete Drupal management capabilities
- Reduces need for users to combine multiple low-level tools for common tasks
- Maintains MCP tool discovery principles while improving usability
