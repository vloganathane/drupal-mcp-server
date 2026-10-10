"""Migration tools for Drupal upgrades and content migration."""


def register_tools(mcp, **deps):
    drush = deps.get("drush_client")
    ai = deps.get("ai_service")

    @mcp.tool()
    async def generate_migration_yaml(migration_type: str, source: dict, destination: dict) -> dict:
        """Generate migration YAML configuration."""
        yaml_content = f"""id: {migration_type}
label: {migration_type}
source:
  plugin: {source.get('plugin', 'd7_node')}
  key: default
destination:
  plugin: entity:node
migration_dependencies: {{}}
"""
        return {"yaml": yaml_content, "type": migration_type}

    @mcp.tool()
    async def generate_module_migration(module_name: str, source_version: str, target_version: str) -> dict:
        """Generate migration module for a custom module."""
        return {
            "module_name": module_name,
            "source_version": source_version,
            "target_version": target_version,
            "files_to_create": [
                f"{module_name}.info.yml",
                f"{module_name}.migration_plugins.yml",
                f"src/Plugin/migrate/source/{module_name}.php",
            ],
        }

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
        return {"returncode": result.get("returncode"), "rolled_back": result.get("returncode") == 0}

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
                    shutil.copy2(src, dst)
                    synced += 1
        return {"synced_files": synced, "source": source_path, "destination": destination_path}

    @mcp.tool()
    async def migrate_taxonomy(vocabularies: list) -> dict:
        """Migrate taxonomy vocabularies."""
        return {"vocabularies": vocabularies, "status": "pending", "migrated": 0}
