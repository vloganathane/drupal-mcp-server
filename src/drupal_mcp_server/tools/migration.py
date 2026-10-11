"""Migration tools for Drupal upgrades and content migration."""

import asyncio


def register_tools(mcp, **deps):
    drush = deps.get("drush_client")
    ai = deps.get("ai_service")

    @mcp.tool()
    async def generate_migration_yaml(migration_type: str, source: dict, destination: dict) -> dict:
        """Generate migration YAML configuration."""
        yaml_content = f"""id: {migration_type}
label: {migration_type}
source:
  plugin: {source.get("plugin", "d7_node")}
  key: default
destination:
  plugin: entity:node
migration_dependencies: {{}}
"""
        return {"yaml": yaml_content, "type": migration_type}

    @mcp.tool()
    async def generate_module_migration(
        module_name: str, source_version: str, target_version: str
    ) -> dict:
        """Generate migration module for a custom module."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            # Create module structure using Drush
            result = await drush.run(
                "generate", ["module", module_name, f"--version={target_version}"]
            )
            if result.get("returncode") != 0:
                return {
                    "error": f"Module generation failed: {result.get('data', {}).get('stderr', '')}"
                }

            # Generate migration plugin boilerplate
            migration_dir = "src/Plugin/migrate/source"
            import os

            os.makedirs(migration_dir, exist_ok=True)

            plugin_content = f"""<?php

namespace Drupal\\{module_name}\\Plugin\\migrate\\source;

use Drupal\\migrate\\Plugin\\migrate\\source\\SqlBase;
use Drupal\\migrate\\Row;

/**
 * Source plugin for {module_name} migration.
 *
 * @MigrateSourcePlugin(
 *   id = "{module_name}",
 *   source_module = "{module_name}"
 * )
 */
class {module_name.capitalize()} extends SqlBase {{

  public function query() {{
    $query = $this->select('{{module_name}}_table', 't')
      ->fields('t');
    return $query;
  }}

  public function fields() {{
    return [
      'id' => $this->t('ID'),
      'title' => $this->t('Title'),
      'body' => $this->t('Body'),
    ];
  }}

  public function prepareRow(Row $row) {{
    // Transform data here if needed
    return parent::prepareRow($row);
  }}

}}
"""
            plugin_path = os.path.join(migration_dir, f"{module_name}.php")
            with open(plugin_path, "w") as f:
                f.write(plugin_content)

            return {
                "module_name": module_name,
                "source_version": source_version,
                "target_version": target_version,
                "files_created": [
                    f"{module_name}.info.yml",
                    f"{module_name}.migration_plugins.yml",
                    f"{plugin_path}",
                ],
                "status": "generated",
            }
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def run_migration_test(migration_id: str, limit: int = 10) -> dict:
        """Test migration with limited records."""
        if not drush:
            return {"error": "Drush not available"}
        result = await drush.run("migrate-import", ["--limit=" + str(limit), migration_id])
        return {"returncode": result.get("returncode"), "data": result.get("data", {})}

    @mcp.tool()
    async def validate_migration(migration_id: str) -> dict:
        """Validate migration configuration."""
        if not drush:
            return {"error": "Drush not available"}
        result = await drush.run("migrate-status", [migration_id])
        return {"returncode": result.get("returncode"), "status": result.get("data", {})}

    @mcp.tool()
    async def rollback_migration(migration_id: str) -> dict:
        """Rollback a completed migration."""
        if not drush:
            return {"error": "Drush not available"}
        result = await drush.run("migrate-rollback", [migration_id])
        return {
            "returncode": result.get("returncode"),
            "rolled_back": result.get("returncode") == 0,
        }

    @mcp.tool()
    async def sync_media_files(source_path: str, destination_path: str) -> dict:
        """Sync media files between paths."""
        import os
        import shutil

        synced = 0
        if os.path.exists(source_path):
            os.makedirs(destination_path, exist_ok=True)
            for f in os.listdir(source_path):
                src = os.path.join(source_path, f)
                dst = os.path.join(destination_path, f)
                if os.path.isfile(src):
                    await asyncio.to_thread(shutil.copy2, src, dst)
                    synced += 1
        return {"synced_files": synced, "source": source_path, "destination": destination_path}

    @mcp.tool()
    async def migrate_taxonomy(vocabularies: list, source_jsonapi: str = None) -> dict:
        """Migrate taxonomy vocabularies."""
        if not jsonapi and not source_jsonapi:
            return {"error": "JSON:API client not available"}
        try:
            migrated = 0
            errors = []

            for vocab in vocabularies:
                try:
                    vid = vocab.get("vid") or vocab.get("id")
                    if not vid:
                        errors.append({"vocabulary": vocab, "error": "Missing vid/id"})
                        continue

                    # Check if vocabulary exists in destination
                    check = await jsonapi.get_by_id("taxonomy_vocabulary", vid)
                    if check.get("error"):
                        # Create vocabulary
                        vocab_data = {
                            "type": "taxonomy_vocabulary--taxonomy_vocabulary",
                            "vid": vid,
                            "name": vocab.get("name", vid),
                            "description": vocab.get("description", ""),
                            "langcode": vocab.get("langcode", "en"),
                        }
                        result = await jsonapi.create_resource("taxonomy_vocabulary", vocab_data)
                        if result.get("error"):
                            errors.append({"vocabulary": vid, "error": result["error"]})
                        else:
                            migrated += 1
                    else:
                        # Update existing vocabulary
                        result = await jsonapi.update_resource("taxonomy_vocabulary", vid, vocab)
                        if result.get("error"):
                            errors.append({"vocabulary": vid, "error": result["error"]})
                        else:
                            migrated += 1
                except Exception as err:
                    errors.append({"vocabulary": vocab.get("vid", "unknown"), "error": str(err)})

            return {
                "vocabularies_processed": len(vocabularies),
                "migrated": migrated,
                "errors": errors,
            }
        except Exception as e:
            return {"error": str(e)}
