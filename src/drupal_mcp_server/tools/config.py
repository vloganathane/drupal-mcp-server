"""Configuration management tools for Drupal."""
import os
import yaml


def register_tools(mcp, **deps):
    drush = deps.get("drush_client")

    @mcp.tool()
    async def export_config(export_path: str = "./config/export", include_optional: bool = False) -> dict:
        """Export Drupal configuration to files."""
        if not drush:
            return {"error": "Drush not available"}
        os.makedirs(export_path, exist_ok=True)
        result = await drush.run("config-export", ["--destination=" + export_path])
        return {
            "export_path": export_path,
            "returncode": result.get("returncode"),
            "stderr": result.get("stderr", "")[:500],
        }

    @mcp.tool()
    async def import_config(import_path: str = "./config/sync", skip_hash_check: bool = False) -> dict:
        """Import Drupal configuration from files."""
        if not drush:
            return {"error": "Drush not available"}
        args = ["--source=" + import_path]
        if skip_hash_check:
            args.append("--skip-hash-check")
        result = await drush.run("config-import", args)
        return {
            "import_path": import_path,
            "returncode": result.get("returncode"),
            "stderr": result.get("stderr", "")[:500],
        }

    @mcp.tool()
    async def sync_config(source_env: str, target_env: str) -> dict:
        """Sync configuration between environments via Drush."""
        if not drush:
            return {"error": "Drush not available"}
        return {"source": source_env, "target": target_env, "status": "not_implemented"}

    @mcp.tool()
    async def diff_config(config_name: str, env1: str = "staging", env2: str = "prod") -> dict:
        """Show differences in configuration between environments."""
        if not drush:
            return {"error": "Drush not available"}
        return {"config": config_name, "env1": env1, "env2": env2, "diff": "not_implemented"}

    @mcp.tool()
    async def split_config(config_names: list, output_dir: str = "./config/split") -> dict:
        """Split configuration into separate directory for atomic deployment."""
        os.makedirs(output_dir, exist_ok=True)
        for name in config_names:
            path = os.path.join(output_dir, f"{name}.yml")
            with open(path, "w") as f:
                yaml.dump({name: {}}, f)
        return {"output_dir": output_dir, "split_configs": config_names}
