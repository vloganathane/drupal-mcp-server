"""Migration tools for Drupal upgrades and content migration."""

import asyncio
import os
import shutil
from typing import Any

from fastmcp import FastMCP

from ._utils import drush_result as _drush_result


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")
    deps.get("ai_service")
    jsonapi = deps.get("jsonapi_client")

    @mcp.tool()
    async def generate_migration_yaml(migration_type: str, source: dict[str, Any], destination: dict[str, Any]) -> dict[str, Any]:
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
        module_name: str, source_version: str, target_version: str, base_path: str = "src/Plugin/migrate/source"
    ) -> dict[str, Any]:
        """Generate migration module for a custom module with source plugin, process plugins, and migration template."""
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
            migration_dir = base_path

            os.makedirs(migration_dir, exist_ok=True)

            # Generate source plugin
            source_plugin = f"""<?php

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
    $query = $this->select('{{{module_name}}}_table', 't')
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
            source_path = os.path.join(migration_dir, f"{module_name}.php")
            with open(source_path, "w") as f:
                f.write(source_plugin)

            # Generate migration YAML template
            migration_yaml_dir = os.path.join(os.path.dirname(migration_dir), "..", "migrations")
            os.makedirs(migration_yaml_dir, exist_ok=True)

            migration_yaml = f"""id: {module_name}
label: {module_name} migration
migration_group: {module_name}
source:
  plugin: {module_name}
  key: default
destination:
  plugin: 'entity:node'
  default_bundle: article
process:
  title: title
  body/value: body
  body/format:
    plugin: default_value
    default_value: basic_html
  uid:
    plugin: default_value
    default_value: 1
  status:
    plugin: default_value
    default_value: true
migration_dependencies: {{}}
"""
            yaml_path = os.path.join(migration_yaml_dir, f"{module_name}.yml")
            with open(yaml_path, "w") as f:
                f.write(migration_yaml)

            # Generate module info.yml if not exists
            info_yml_path = os.path.join(os.path.dirname(migration_dir), "..", f"{module_name}.info.yml")
            if not os.path.exists(info_yml_path):
                info_yml = f"""name: {module_name}
type: module
description: Migration module for {module_name}
core_version_requirement: ^{target_version}
package: Migration
dependencies:
  - migrate
  - migrate_plus
  - migrate_tools
"""
                with open(info_yml_path, "w") as f:
                    f.write(info_yml)

            # Generate .module file with hook_migrate_api
            module_file_path = os.path.join(os.path.dirname(migration_dir), "..", f"{module_name}.module")
            if not os.path.exists(module_file_path):
                module_file = f"""<?php

/**
 * @file
 * {module_name} migration module.
 */

/**
 * Implements hook_migrate_api().
 */
function {module_name}_migrate_api() {{
  return [
    'api' => 2,
    'groups' => [
      '{module_name}' => [
        'title' => t('{module_name} migrations'),
      ],
    ],
    'migrations' => [
      '{module_name}' => [
        'class' => null,
        'group' => '{module_name}',
      ],
    ],
  ];
}}
"""
                with open(module_file_path, "w") as f:
                    f.write(module_file)

            return {
                "module_name": module_name,
                "source_version": source_version,
                "target_version": target_version,
                "files_created": [
                    f"src/Plugin/migrate/source/{module_name}.php",
                    f"migrations/{module_name}.yml",
                    f"{module_name}.info.yml",
                    f"{module_name}.module",
                ],
                "status": "generated",
                "notes": "Generated source plugin, migration YAML, info.yml, and module file with hook_migrate_api",
            }
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def run_migration_test(migration_id: str, limit: int = 10) -> dict[str, Any]:
        """Test migration with limited records."""
        if not drush:
            return {"error": "Drush not available"}
        result = await drush.run("migrate-import", ["--limit=" + str(limit), migration_id])
        return _drush_result(result, migration_id=migration_id)

    @mcp.tool()
    async def validate_migration(migration_id: str) -> dict[str, Any]:
        """Validate migration configuration."""
        if not drush:
            return {"error": "Drush not available"}
        result = await drush.run("migrate-status", [migration_id])
        return _drush_result(result, status=result.get("data", {}), migration_id=migration_id)

    @mcp.tool()
    async def rollback_migration(migration_id: str) -> dict[str, Any]:
        """Rollback a completed migration."""
        if not drush:
            return {"error": "Drush not available"}
        result = await drush.run("migrate-rollback", [migration_id])
        return _drush_result(
            result,
            rolled_back=result.get("returncode") == 0,
            migration_id=migration_id,
        )

    @mcp.tool()
    async def sync_media_files(source_path: str, destination_path: str) -> dict[str, Any]:
        """Sync media files between paths."""

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
    async def migrate_taxonomy(
        vocabularies: list[dict[str, Any]],
        source_jsonapi: str | None = None,
        include_terms: bool = True,
    ) -> dict[str, Any]:
        """Migrate taxonomy vocabularies and their terms."""
        if not jsonapi and not source_jsonapi:
            return {"error": "JSON:API client not available"}
        if not jsonapi:
            return {"error": "JSON:API client not available"}
        try:
            vocab_migrated = 0
            term_migrated = 0
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
                            vocab_migrated += 1
                    else:
                        # Update existing vocabulary
                        result = await jsonapi.update_resource("taxonomy_vocabulary", vid, vocab)
                        if result.get("error"):
                            errors.append({"vocabulary": vid, "error": result["error"]})
                        else:
                            vocab_migrated += 1

                    # Migrate terms if requested
                    if include_terms and "terms" in vocab:
                        terms = vocab["terms"]
                        for term in terms:
                            try:
                                tid = term.get("tid") or term.get("id")
                                if not tid:
                                    errors.append({"vocabulary": vid, "term": term, "error": "Missing tid/id"})
                                    continue

                                # Check if term exists
                                term_check = await jsonapi.get_by_id(f"taxonomy_term--{vid}", tid)
                                term_data = {
                                    "type": f"taxonomy_term--{vid}",
                                    "tid": tid,
                                    "name": term.get("name", ""),
                                    "description": term.get("description", ""),
                                    "langcode": term.get("langcode", "en"),
                                    "parent": term.get("parent", []),
                                    "weight": term.get("weight", 0),
                                }
                                if term_check.get("error"):
                                    result = await jsonapi.create_resource(f"taxonomy_term--{vid}", term_data)
                                else:
                                    result = await jsonapi.update_resource(f"taxonomy_term--{vid}", tid, term_data)

                                if result.get("error"):
                                    errors.append({"vocabulary": vid, "term": tid, "error": result["error"]})
                                else:
                                    term_migrated += 1
                            except Exception as term_err:
                                errors.append({"vocabulary": vid, "term": term.get("tid", "unknown"), "error": str(term_err)})

                except Exception as err:
                    errors.append({"vocabulary": vocab.get("vid", "unknown"), "error": str(err)})

            return {
                "vocabularies_processed": len(vocabularies),
                "vocabularies_migrated": vocab_migrated,
                "terms_migrated": term_migrated,
                "errors": errors,
            }
        except Exception as e:
            return {"error": str(e)}
