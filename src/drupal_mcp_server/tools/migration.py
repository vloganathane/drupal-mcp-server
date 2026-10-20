"""Migration tools for Drupal upgrades and content migration."""

import asyncio
import os
import re
import shutil
from typing import Any

import yaml
from fastmcp import FastMCP

from ._utils import drush_result as _drush_result


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")
    deps.get("ai_service")
    jsonapi = deps.get("jsonapi_client")

    migration_service = deps.get("migration_service")
    if migration_service is None:
        from ..services.migration_service import MigrationService

        migration_service = MigrationService(
            storage_dir=os.environ.get("DRUPAL_MCP_MIGRATION_DIR")
        )

    @mcp.tool()
    async def generate_migration_yaml(migration_type: str, source: dict[str, Any], destination: dict[str, Any]) -> dict[str, Any]:
        """Generate migration YAML configuration."""
        # The id is config Drupal's migrate storage must load: interpolated
        # unvalidated it was neither (spaces are not machine names), and a
        # value carrying a newline injected keys into this very document.
        if not re.fullmatch(r"[a-z0-9_]+", migration_type):
            return {
                "error": (
                    f"Invalid migration id {migration_type!r}: use lowercase "
                    "letters, digits and underscores"
                )
            }
        # The caller's source and destination blocks are the point of the
        # tool: destination was accepted and ignored (the plugin was
        # hardcoded to entity:node), and hand-rolled f-string YAML broke on
        # any value containing ": ".
        config: dict[str, Any] = {
            "id": migration_type,
            "label": migration_type,
            "source": {"plugin": "d7_node", "key": "default", **source},
            "destination": {"plugin": "entity:node", **destination},
            "migration_dependencies": {},
        }
        return {"yaml": yaml.dump(config, sort_keys=False), "type": migration_type}

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

            # PSR-4 both ways round: the class is StudlyCase and the
            # file holding it carries the same name — "migrate_d7_nodes.php"
            # with class Migrate_d7_nodes is never autoloadable on a
            # case-sensitive filesystem — and the MigrateSourcePlugin
            # annotation must be imported or discovery cannot resolve it.
            class_name = "".join(part.capitalize() for part in module_name.split("_"))
            source_plugin = f"""<?php

namespace Drupal\\{module_name}\\Plugin\\migrate\\source;

use Drupal\\migrate\\Annotation\\MigrateSourcePlugin;
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
class {class_name} extends SqlBase {{

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
            source_path = os.path.join(migration_dir, f"{class_name}.php")
            with open(source_path, "w") as f:
                f.write(source_plugin)

            # Sidecar files belong at the module root — migrations/, the
            # info.yml and the .module — where the report says they are
            # and where Drupal looks. base_path points inside the
            # module's src tree, so the root is base_path minus the
            # plugin directory; without that suffix, the cwd.
            plugin_suffix = os.path.join("src", "Plugin", "migrate", "source")
            root_prefix = (
                base_path[: -len(plugin_suffix)] if base_path.endswith(plugin_suffix) else ""
            )
            module_root = os.path.normpath(root_prefix)  # "" -> "."
            migration_yaml_dir = os.path.join(module_root, "migrations")
            os.makedirs(migration_yaml_dir, exist_ok=True)

            # Generate migration YAML template
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
            info_yml_path = os.path.join(module_root, f"{module_name}.info.yml")
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
            module_file_path = os.path.join(module_root, f"{module_name}.module")
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
                    os.path.normpath(source_path),
                    os.path.normpath(yaml_path),
                    os.path.normpath(info_yml_path),
                    os.path.normpath(module_file_path),
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
        if not os.path.isdir(source_path):
            # A silent "synced: 0" made a typo'd path look like a source
            # directory that simply held no files.
            return {
                "error": f"Source path not found or not a directory: {source_path}",
                "source": source_path,
                "destination": destination_path,
            }

        os.makedirs(destination_path, exist_ok=True)
        synced = 0
        skipped = 0
        errors: list[dict[str, Any]] = []
        for f in os.listdir(source_path):
            src = os.path.join(source_path, f)
            dst = os.path.join(destination_path, f)
            if not os.path.isfile(src):
                continue
            if os.path.abspath(src) == os.path.abspath(dst):
                # Syncing a directory onto itself: copy2 raises
                # SameFileError, which used to abort the run mid-list.
                skipped += 1
                continue
            try:
                await asyncio.to_thread(shutil.copy2, src, dst)
                synced += 1
            except Exception as exc:  # noqa: BLE001
                # One unreadable file must not abandon the rest.
                errors.append({"file": f, "error": str(exc)})
        payload: dict[str, Any] = {
            "synced_files": synced,
            "source": source_path,
            "destination": destination_path,
        }
        if skipped:
            payload["skipped_files"] = skipped
        if errors:
            payload["errors"] = errors
        return payload

    @mcp.tool()
    async def migrate_taxonomy(
        vocabularies: list[dict[str, Any]],
        include_terms: bool = True,
    ) -> dict[str, Any]:
        """Migrate taxonomy vocabularies and their terms to this site.

        Each vocabulary carries ``vid``/``id``, ``name``, ``description``
        and optional ``terms``. A term's ``tid``/``id`` is used only to
        find an existing term: JSON:API treats it as read-only and
        rejects it as a settable attribute.
        """
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

                    vocab_data = {
                        "type": "taxonomy_vocabulary--taxonomy_vocabulary",
                        "vid": vid,
                        "name": vocab.get("name", vid),
                        "description": vocab.get("description", ""),
                        "langcode": vocab.get("langcode", "en"),
                    }
                    # get_by_id answers with the resource or raises
                    # LookupError for a missing id — it never returns an
                    # error dict, so branching on check["error"] left the
                    # create paths dead: an absent vocabulary was reported
                    # as an error instead of being created, on every call.
                    try:
                        await jsonapi.get_by_id("taxonomy_vocabulary", vid)
                    except LookupError:
                        result = await jsonapi.create_resource(
                            "taxonomy_vocabulary", vocab_data
                        )
                    except Exception as err:  # noqa: BLE001
                        errors.append({"vocabulary": vid, "error": str(err)})
                        continue
                    else:
                        # The cleaned payload, not the caller's dict: the
                        # raw dict carries its `terms` list, which is not a
                        # vocabulary attribute and 400s the update.
                        result = await jsonapi.update_resource(
                            "taxonomy_vocabulary", vid, vocab_data
                        )
                    if isinstance(result, dict) and result.get("error"):
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

                                term_data = {
                                    "type": f"taxonomy_term--{vid}",
                                    "name": term.get("name", ""),
                                    "description": term.get("description", ""),
                                    "langcode": term.get("langcode", "en"),
                                    "parent": term.get("parent", []),
                                    "weight": term.get("weight", 0),
                                }
                                # Same contract as the vocabulary: the
                                # lookup raises for a missing term, so the
                                # existence test decides create vs update —
                                # and `tid` stays out of the payload, where
                                # JSON:API rejects it as read-only.
                                try:
                                    await jsonapi.get_by_id(f"taxonomy_term--{vid}", tid)
                                except LookupError:
                                    result = await jsonapi.create_resource(
                                        f"taxonomy_term--{vid}", term_data
                                    )
                                except Exception as term_err:  # noqa: BLE001
                                    errors.append({"vocabulary": vid, "term": tid, "error": str(term_err)})
                                    continue
                                else:
                                    result = await jsonapi.update_resource(
                                        f"taxonomy_term--{vid}", tid, term_data
                                    )

                                if isinstance(result, dict) and result.get("error"):
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

    @mcp.tool()
    async def create_migration_plan(
        migration_id: str,
        source: dict[str, Any] | None = None,
        target: dict[str, Any] | None = None,
        entities: list[str] | None = None,
        field_mappings: dict[str, Any] | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        """Create or replace a persisted migration plan."""
        if not migration_service:
            return {"error": "Migration service not available"}
        try:
            return migration_service.create_plan(
                migration_id=migration_id,
                source=source,
                target=target,
                entities=entities,
                field_mappings=field_mappings,
                notes=notes,
            )
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    @mcp.tool()
    async def get_migration_plan(migration_id: str) -> dict[str, Any]:
        """Read a persisted migration plan and its tracked state."""
        if not migration_service:
            return {"error": "Migration service not available"}
        return migration_service.get_plan(migration_id)

    @mcp.tool()
    async def list_migration_plans() -> list[dict[str, Any]]:
        """List all persisted migration plans."""
        if not migration_service:
            return [{"error": "Migration service not available"}]
        return migration_service.list_plans()

    @mcp.tool()
    async def migration_status(migration_id: str) -> dict[str, Any]:
        """Summarize migration progress for a persisted plan."""
        if not migration_service:
            return {"error": "Migration service not available"}
        return migration_service.migration_status(migration_id)

    @mcp.tool()
    async def migrate_records(
        migration_id: str,
        entity_type: str,
        records: list[dict[str, Any]],
        field_mapping: dict[str, str] | None = None,
        idempotency_key: str = "id",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Copy a batch of source records into the target Drupal site through JSON:API."""
        if not migration_service:
            return {"error": "Migration service not available"}
        try:
            return await migration_service.migrate_records(
                migration_id=migration_id,
                entity_type=entity_type,
                records=records,
                field_mapping=field_mapping,
                idempotency_key=idempotency_key,
                dry_run=dry_run,
            )
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    @mcp.tool()
    async def record_migration_result(
        migration_id: str,
        entity_type: str,
        legacy_id: str,
        target_id: str | None = None,
        status: str = "created",
        error: str | None = None,
    ) -> dict[str, Any]:
        """Record the outcome of a manually executed migration operation."""
        if not migration_service:
            return {"error": "Migration service not available"}
        try:
            return migration_service.record_entity_result(
                migration_id=migration_id,
                entity_type=entity_type,
                legacy_id=legacy_id,
                target_id=target_id,
                status=status,
                error=error,
            )
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    @mcp.tool()
    async def analyze_source_site(
        migration_id: str | None = None,
        source_url: str = "",
        resource_type: str = "node--article",
        token: str | None = None,
        verify_tls: bool = True,
        username: str | None = None,
        password: str | None = None,
    ) -> dict[str, Any]:
        """Analyze a source Drupal JSON:API resource type and optionally store counts in a plan.

        ``username``/``password`` authenticate to the source site: JSON:API
        field access hides attributes (user name/mail, for example) from
        anonymous requests, so unauthenticated analysis under-reports.
        """
        if not migration_service:
            return {"error": "Migration service not available"}
        if not source_url:
            return {"error": "source_url is required"}
        try:
            return await migration_service.analyze_source_site(
                source_url=source_url,
                resource_type=resource_type,
                token=token,
                migration_id=migration_id,
                verify_tls=verify_tls,
                username=username,
                password=password,
            )
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    @mcp.tool()
    async def reconcile_migration_counts(
        migration_id: str,
        target_resource_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """Compare recorded source counts with current target-site counts."""
        if not migration_service:
            return {"error": "Migration service not available"}
        try:
            return await migration_service.reconcile_counts(
                migration_id=migration_id,
                target_resource_types=target_resource_types,
            )
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    @mcp.tool()
    async def run_migration_wave(
        migration_id: str,
        resource_type: str,
        batch_size: int = 100,
        dry_run: bool = False,
        source_token: str | None = None,
        verify_tls: bool = True,
        source_username: str | None = None,
        source_password: str | None = None,
        field_mapping: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Fetch and migrate one resource type from the plan's source site into the target site.

        ``source_username``/``source_password`` authenticate to the source
        site. Credentials may instead be stored in the plan's ``source`` block
        (``username``/``password``), which keeps waves self-contained.
        """
        if not migration_service:
            return {"error": "Migration service not available"}
        try:
            return await migration_service.run_migration_wave(
                migration_id=migration_id,
                resource_type=resource_type,
                batch_size=batch_size,
                dry_run=dry_run,
                source_token=source_token,
                verify_tls=verify_tls,
                source_username=source_username,
                source_password=source_password,
                field_mapping=field_mapping,
            )
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    @mcp.tool()
    async def run_migration(
        migration_id: str,
        entity_types: list[str] | None = None,
        dry_run: bool = False,
        source_token: str | None = None,
        verify_tls: bool = True,
        source_username: str | None = None,
        source_password: str | None = None,
        continue_on_error: bool = False,
    ) -> dict[str, Any]:
        """Run an ordered end-to-end migration for one or all planned entity types.

        Waves run in the order given (dependencies first). A failed wave stops
        the run by default, since a schema or auth problem tends to repeat;
        set ``continue_on_error`` to attempt the remaining types anyway.
        """
        if not migration_service:
            return {"error": "Migration service not available"}
        try:
            return await migration_service.run_migration(
                migration_id=migration_id,
                entity_types=entity_types,
                dry_run=dry_run,
                source_token=source_token,
                verify_tls=verify_tls,
                source_username=source_username,
                source_password=source_password,
                continue_on_error=continue_on_error,
            )
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}
