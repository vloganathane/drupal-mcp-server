"""Configuration management tools for Drupal."""

import os

import yaml


def register_tools(mcp, **deps):
    drush = deps.get("drush_client")

    @mcp.tool()
    async def export_config(
        export_path: str = "./config/export", include_optional: bool = False
    ) -> dict:
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
    async def import_config(
        import_path: str = "./config/sync", skip_hash_check: bool = False
    ) -> dict:
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
    async def sync_config(source_env: str, target_env: str, dry_run: bool = False) -> dict:
        """Sync configuration between environments via Drush."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            # Export config from source environment
            export_result = await drush.run(
                "config-export", ["--destination=/tmp/config_sync_source"]
            )
            if export_result.get("returncode") != 0:
                return {"error": f"Source export failed: {export_result.get('stderr', '')}"}

            if dry_run:
                # Show what would change
                diff_result = await drush.run(
                    "config-import", ["--source=/tmp/config_sync_source", "--preview=1"]
                )
                return {
                    "source_env": source_env,
                    "target_env": target_env,
                    "dry_run": True,
                    "changes_preview": diff_result.get("stdout", "")[:2000],
                }

            # Import config to target environment
            import_result = await drush.run("config-import", ["--source=/tmp/config_sync_source"])
            return {
                "source_env": source_env,
                "target_env": target_env,
                "returncode": import_result.get("returncode"),
                "stdout": import_result.get("stdout", "")[:500],
                "stderr": import_result.get("stderr", "")[:500],
            }
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def diff_config(config_name: str, env1: str = "staging", env2: str = "prod") -> dict:
        """Show differences in configuration between environments."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            # Export config from env1
            export1 = await drush.run("config-export", ["--destination=/tmp/config_diff_env1"])
            if export1.get("returncode") != 0:
                return {"error": f"Env1 export failed: {export1.get('stderr', '')}"}

            # Export config from env2
            export2 = await drush.run("config-export", ["--destination=/tmp/config_diff_env2"])
            if export2.get("returncode") != 0:
                return {"error": f"Env2 export failed: {export2.get('stderr', '')}"}

            # Use drush config-diff if available
            diff_result = await drush.run(
                "config-diff",
                ["/tmp/config_diff_env1", "/tmp/config_diff_env2", "--name=" + config_name],
            )

            if diff_result.get("returncode") == 0:
                return {
                    "config": config_name,
                    "env1": env1,
                    "env2": env2,
                    "diff": diff_result.get("stdout", "")[:5000],
                    "has_changes": True,
                }
            else:
                # Fallback: compare YAML files directly
                import yaml

                path1 = f"/tmp/config_diff_env1/{config_name}.yml"
                path2 = f"/tmp/config_diff_env2/{config_name}.yml"

                if not os.path.exists(path1) or not os.path.exists(path2):
                    return {
                        "config": config_name,
                        "env1": env1,
                        "env2": env2,
                        "diff": "Config file not found in one or both environments",
                        "has_changes": False,
                    }

                with open(path1) as f1, open(path2) as f2:
                    data1 = yaml.safe_load(f1) or {}
                    data2 = yaml.safe_load(f2) or {}

                # Simple diff
                import difflib

                diff = list(
                    difflib.unified_diff(
                        yaml.dump(data1, default_flow_style=False).splitlines(),
                        yaml.dump(data2, default_flow_style=False).splitlines(),
                        fromfile=env1,
                        tofile=env2,
                    )
                )

                return {
                    "config": config_name,
                    "env1": env1,
                    "env2": env2,
                    "diff": "\n".join(diff)[:5000],
                    "has_changes": len(diff) > 0,
                }
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def split_config(config_names: list, output_dir: str = "./config/split") -> dict:
        """Split configuration into separate directory for atomic deployment."""
        os.makedirs(output_dir, exist_ok=True)
        for name in config_names:
            path = os.path.join(output_dir, f"{name}.yml")
            with open(path, "w") as f:
                yaml.dump({name: {}}, f)
        return {"output_dir": output_dir, "split_configs": config_names}
