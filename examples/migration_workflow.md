# Drupal 7 to Drupal 10 Migration Workflow

Complete workflow using Drupal MCP Server tools.

## Step 1: Analyze Source Site

```
analyze_d7_site(
    site_url="https://old-site.com",
    include_modules=True,
    include_content=True
)
```

**Output**: Upgrade readiness report with module inventory.

## Step 2: Map Modules to D10 Equivalents

```
map_modules_d7_to_d10(
    module_list=["views", "ctools", "date", "webform"],
    ai_provider="ollama"
)
```

**Output**: AI-generated module mapping with alternatives.

## Step 3: Find Deprecated Code

```
find_deprecated_code(
    site_path="/path/to/d7/custom/modules",
    scan_custom_modules=True
)
```

**Output**: List of deprecated API usage with replacements.

## Step 4: Generate Migration YAML

```
generate_migration_yaml(
    source_site="https://old-site.com",
    entity_type="node",
    bundle="article"
)
```

**Output**: Migration configuration YAML files.

## Step 5: Test Migration (Dry Run)

```
run_migration_test(
    migration_id="migrate_article",
    sample_size=10
)
```

**Output**: Test results with validation report.

## Step 6: Execute Migration

```
execute_migration(
    migration_id="migrate_article",
    batch_size=50,
    rollback_on_error=True
)
```

**Output**: Migration progress and error log.

## Step 7: Validate Migrated Content

```
validate_migration(
    migration_id="migrate_article",
    check_fields=True,
    check_media=True
)
```

**Output**: Validation report comparing source/target.

## Step 8: AI-Powered Content Cleanup

```
clean_nodes_ai(
    content_type="article",
    cleanup_type="remove_inline_styles",
    ai_provider="ollama"
)
```

**Output**: Cleaned content report.

---

## Complete Example Script

```python
#!/usr/bin/env python3
"""D7 → D10 migration orchestration."""

async def migrate_drupal_site():
    # 1. Analyze
    analysis = await analyze_d7_site(
        site_url="https://old.example.com"
    )
    
    # 2. Map modules
    modules = analysis["modules"]
    mapping = await map_modules_d7_to_d10(
        module_list=list(modules.keys())
    )
    
    # 3. Generate migration config
    for content_type in ["article", "page", "blog"]:
        await generate_migration_yaml(
            source_site="https://old.example.com",
            entity_type="node",
            bundle=content_type
        )
    
    # 4. Test first
    test = await run_migration_test(
        migration_id="migrate_article",
        sample_size=10
    )
    
    if test["success_rate"] > 0.9:
        # 5. Execute
        await execute_migration(
            migration_id="migrate_article"
        )
        
        # 6. Validate
        await validate_migration(
            migration_id="migrate_article"
        )
        
        # 7. AI cleanup
        await clean_nodes_ai(
            content_type="article",
            cleanup_type="remove_inline_styles"
        )

if __name__ == "__main__":
    asyncio.run(migrate_drupal_site())
```

## Tips

- Always run `analyze_d7_site` first to understand scope
- Use `run_migration_test` before full migration
- Enable `rollback_on_error` for safety
- Run AI cleanup tools after migration for quality
- Backup database before starting (`backup_database`)
