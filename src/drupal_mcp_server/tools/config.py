"""Configuration management tools for Drupal."""

import os
from typing import Any

import yaml
from fastmcp import FastMCP

from ._utils import drush_output as _output
from ._utils import drush_result as _drush_result


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")

    @mcp.tool()
    async def config_get(name: str) -> dict[str, Any]:
        """Get a single configuration object by name."""
        if not drush:
            return {
                "error": (
                    "Drush not available. Config objects are not exposed by "
                    "JSON:API, so this tool needs `drush config:get`."
                )
            }
        try:
            result = await drush.run("config:get", [name])
            if result.get("returncode") != 0:
                return {
                    "error": (
                        f"drush config:get {name} failed: "
                        f"{result.get('stderr', '')}".strip()
                    )
                }
            return {"name": name, "config": result.get("data")}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def config_set(name: str, value: dict[str, Any]) -> dict[str, Any]:
        """Set a single configuration value."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            # Use drush config:set for individual config values
            # Format: drush config:set config.name key value
            for key, val in value.items():
                result = await drush.run("config:set", [name, key, str(val)])
                if result.get("returncode") != 0:
                    return {"error": f"Failed to set {name}.{key}: {result.get('stderr', '')}"}
            return {"success": True, "config": name, "updated": list(value.keys())}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def export_config(
        export_path: str = "./config/export", include_optional: bool = False
    ) -> dict[str, Any]:
        """Export Drupal configuration to files."""
        if not drush:
            return {"error": "Drush not available"}
        os.makedirs(export_path, exist_ok=True)
        result = await drush.run("config-export", ["--destination=" + export_path])
        return _drush_result(result, export_path=export_path)

    @mcp.tool()
    async def import_config(
        import_path: str = "./config/sync", skip_hash_check: bool = False
    ) -> dict[str, Any]:
        """Import Drupal configuration from files."""
        if not drush:
            return {"error": "Drush not available"}
        args = ["--source=" + import_path]
        if skip_hash_check:
            args.append("--skip-hash-check")
        result = await drush.run("config-import", args)
        return _drush_result(result, import_path=import_path)

    @mcp.tool()
    async def sync_config(source_env: str, target_env: str, dry_run: bool = False) -> dict[str, Any]:
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
                    "changes_preview": _output(diff_result)[:2000],
                }

            # Import config to target environment
            import_result = await drush.run("config-import", ["--source=/tmp/config_sync_source"])
            return {
                "source_env": source_env,
                "target_env": target_env,
                "returncode": import_result.get("returncode"),
                "stdout": _output(import_result)[:500],
                "stderr": import_result.get("stderr", "")[:500],
            }
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def diff_config(config_name: str, env1: str = "staging", env2: str = "prod") -> dict[str, Any]:
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
                has_changes = bool(_output(diff_result).strip())
                return {
                    "config": config_name,
                    "env1": env1,
                    "env2": env2,
                    "diff": _output(diff_result)[:5000],
                    "has_changes": has_changes,
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
    async def split_config(
        config_names: list[str], output_dir: str = "./config/split", source_dir: str = "./config/sync"
    ) -> dict[str, Any]:
        """Split configuration into separate directories for atomic deployment.
        
        Reads from source_dir (exported config) and creates individual config
        files in output_dir for each specified config object.
        """
        if not os.path.exists(source_dir):
            return {"error": f"Source config directory not found: {source_dir}"}

        os.makedirs(output_dir, exist_ok=True)
        split_files = []
        missing = []

        for name in config_names:
            # Config files are typically named like: system.site.yml, node.type.article.yml
            # We need to find the matching file
            found = False
            for filename in os.listdir(source_dir):
                if filename.endswith(".yml") or filename.endswith(".yaml"):
                    # Check if this file contains the config we want
                    filepath = os.path.join(source_dir, filename)
                    try:
                        with open(filepath) as f:
                            data = yaml.safe_load(f)
                        if data and isinstance(data, dict):
                            # Config files often have the config name as a key
                            # or the filename matches the pattern
                            if name in data or name.replace(".", "_") in filename:
                                dest_path = os.path.join(output_dir, filename)
                                with open(dest_path, "w") as out:
                                    yaml.dump(data, out, default_flow_style=False)
                                split_files.append({"config": name, "file": filename, "path": dest_path})
                                found = True
                                break
                    except Exception:
                        continue
            
            if not found:
                # Try exact filename match
                exact_file = f"{name}.yml"
                if os.path.exists(os.path.join(source_dir, exact_file)):
                    dest_path = os.path.join(output_dir, exact_file)
                    with open(os.path.join(source_dir, exact_file)) as src, open(dest_path, "w") as dst:
                        dst.write(src.read())
                    split_files.append({"config": name, "file": exact_file, "path": dest_path})
                    found = True
            
            if not found:
                missing.append(name)

        return {
            "output_dir": output_dir,
            "source_dir": source_dir,
            "split_configs": split_files,
            "missing_configs": missing,
            "total_split": len(split_files),
        }

    @mcp.tool()
    async def config_status() -> dict[str, Any]:
        """Compare active configuration with the exported sync directory.

        Read-only: reports how many config objects are the same, differ,
        exist only in the database (never exported, or changed since), or
        exist only in the sync directory, with the differing names. This is
        what `drush config:import` would act on; nothing is exported,
        imported, or written here.

        An empty sync directory shows everything as "Only in DB" -- export
        first with `drush config:export` (or the `export_config` tool)
        before expecting a useful comparison.
        """
        if not drush:
            return {"error": "Drush not available"}
        result = await drush.run("config:status", ["--format=json"])
        if result.get("returncode"):
            return _drush_result(result)

        data = result.get("data")
        states: dict[str, list[str]] = {}
        if isinstance(data, dict):
            for name, row in data.items():
                state = row.get("state") if isinstance(row, dict) else str(row)
                states.setdefault(str(state), []).append(str(name))
        elif isinstance(data, list):
            for row in data:
                if isinstance(row, dict):
                    states.setdefault(str(row.get("state", "unknown")), []).append(
                        str(row.get("name", ""))
                    )
        else:
            return {
                "note": "drush config:status returned no recognisable data",
                "output": _drush_result(result)["output"],
            }

        payload: dict[str, Any] = {
            "counts": {state: len(names) for state, names in states.items()},
            "objects": {
                state: {
                    "count": len(names),
                    "names": names[:200],
                    "truncated": len(names) > 200,
                }
                for state, names in states.items()
            },
            "total": sum(len(names) for names in states.values()),
        }
        only_db = len(states.get("Only in DB", []))
        if payload["total"] and only_db == payload["total"]:
            payload["note"] = (
                "Every config object is 'Only in DB': the sync directory is "
                "empty or was never exported, so there is nothing to "
                "compare against."
            )
        return payload
