"""DevOps tools for Drupal (Drush, DDEV, etc.)."""

import os
import subprocess
from typing import Any

from fastmcp import FastMCP


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")
    site_manager = deps.get("site_manager")

    @mcp.tool()
    async def drush_command(command: str, args: list[str] | None = None, options: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute any Drush command."""
        if not drush:
            return {"error": "Drush not available"}
        cmd_args = args or []
        if options:
            for k, v in options.items():
                cmd_args.append(f"--{k}={v}" if v else f"--{k}")
        return await drush.run(command, cmd_args)  # type: ignore[no-any-return]

    @mcp.tool()
    async def ddev_setup(
        project_name: str = ".", drupal_version: str = "10", webroot: str = "web"
    ) -> dict[str, Any]:
        """Generate .ddev/config.yaml for local Drupal env."""
        site_manager = deps.get("site_manager")
        if not site_manager:
            return {"error": "Site manager not available"}
        import os

        ddev_config = f"""name: {project_name}
kind: drupal{drupal_version}
webroot: {webroot}
"""
        config_path = os.path.join(project_name, ".ddev", "config.yaml")
        try:
            os.makedirs(os.path.dirname(config_path) or ".", exist_ok=True)
            with open(config_path, "w") as f:
                f.write(ddev_config)
            return {
                "status": "created",
                "path": config_path,
                "project": project_name,
                "version": drupal_version,
            }
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def ddev_start(project_name: str = ".") -> dict[str, Any]:
        """Start DDEV project."""
        if not site_manager:
            return {"error": "Site manager not available"}
        return await site_manager.ddev_start()  # type: ignore[no-any-return]

    @mcp.tool()
    async def ddev_stop(project_name: str = ".") -> dict[str, Any]:
        """Stop DDEV project."""
        if not site_manager:
            return {"error": "Site manager not available"}
        return await site_manager.ddev_stop()  # type: ignore[no-any-return]

    @mcp.tool()
    async def ddev_exec(command: str, project_name: str = ".") -> dict[str, Any]:
        """Execute command in DDEV container."""
        if not site_manager:
            return {"error": "Site manager not available"}
        return await site_manager.ddev_exec(command)  # type: ignore[no-any-return]

    @mcp.tool()
    async def lando_start(project_name: str = ".") -> dict[str, Any]:
        """Start Lando project."""
        if not site_manager:
            return {"error": "Site manager not available"}
        return await site_manager.lando_start()  # type: ignore[no-any-return]

    @mcp.tool()
    async def lando_stop(project_name: str = ".") -> dict[str, Any]:
        """Stop Lando project."""
        if not site_manager:
            return {"error": "Site manager not available"}
        return await site_manager.lando_stop()  # type: ignore[no-any-return]

    @mcp.tool()
    async def lando_exec(command: str, project_name: str = ".") -> dict[str, Any]:
        """Execute command in Lando container."""
        if not site_manager:
            return {"error": "Site manager not available"}
        return await site_manager.lando_exec(command)  # type: ignore[no-any-return]

    @mcp.tool()
    async def lando_setup(
        project_name: str = ".", drupal_version: str = "10", webroot: str = "web"
    ) -> dict[str, Any]:
        """Generate .lando.yml for local Drupal env."""
        site_manager = deps.get("site_manager")
        if not site_manager:
            return {"error": "Site manager not available"}
        import os

        lando_config = f"""name: {project_name}
recipe: drupal{drupal_version}
webroot: {webroot}
"""
        config_path = os.path.join(project_name, ".lando.yml")
        try:
            with open(config_path, "w") as f:
                f.write(lando_config)
            return {"status": "created", "path": config_path, "project": project_name}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def acquia_deploy(
        environment: str,
        branch: str = "main",
        site_id: str | None = None,
        code_path: str = ".",
        database_name: str | None = None,
        wait_for_completion: bool = True,
        timeout: int = 600,
    ) -> dict[str, Any]:
        """Deploy to Acquia Cloud via acquia-cli or Drush acquia integration.
        
        Supports both acquia-cli (preferred) and legacy Drush acquia commands.
        """
        if not drush:
            return {"error": "Drush not available"}
        if not site_id:
            return {
                "error": "site_id required for Acquia deploy. Provide via Acquia Cloud Platform UI or DRUPAL_ACQUIA_SITE_ID env var."
            }

        results: dict[str, Any] = {
            "site_id": site_id,
            "environment": environment,
            "branch": branch,
            "steps": [],
        }

        try:
            # Step 1: Check if acquia-cli is available
            cli_check = await drush.run("acquia-cli", ["--version"])
            has_acquia_cli = cli_check.get("returncode") == 0

            if has_acquia_cli:
                # Use acquia-cli (modern approach)
                results["method"] = "acquia-cli"
                
                # Deploy code
                deploy_result = await drush.run(
                    "acquia-cli",
                    [
                        "code:deploy",
                        f"--site={site_id}",
                        f"--environment={environment}",
                        f"--branch={branch}",
                        f"--source={code_path}",
                    ],
                )
                results["steps"].append({"step": "code_deploy", "result": deploy_result})
                
                if deploy_result.get("returncode") != 0:
                    results["error"] = "Code deployment failed"
                    return results

                # If database name provided, deploy database
                if database_name:
                    db_result = await drush.run(
                        "acquia-cli",
                        [
                            "database:import",
                            f"--site={site_id}",
                            f"--environment={environment}",
                            f"--database={database_name}",
                        ],
                    )
                    results["steps"].append({"step": "database_import", "result": db_result})

                # Run database updates
                updb_result = await drush.run(
                    "acquia-cli",
                    [
                        "command:run",
                        f"--site={site_id}",
                        f"--environment={environment}",
                        "--command=drush updb -y",
                    ],
                )
                results["steps"].append({"step": "database_updates", "result": updb_result})

                # Clear cache
                cache_result = await drush.run(
                    "acquia-cli",
                    [
                        "command:run",
                        f"--site={site_id}",
                        f"--environment={environment}",
                        "--command=drush cr",
                    ],
                )
                results["steps"].append({"step": "cache_rebuild", "result": cache_result})

                # Wait for completion if requested
                if wait_for_completion:
                    # Check deployment status
                    status_result = await drush.run(
                        "acquia-cli",
                        [
                            "deploy:status",
                            f"--site={site_id}",
                            f"--environment={environment}",
                            f"--timeout={timeout}",
                        ],
                    )
                    results["steps"].append({"step": "wait_for_deploy", "result": status_result})

            else:
                # Fallback to legacy Drush acquia commands
                results["method"] = "legacy_drush"
                
                # Check if drush acquia command exists
                acquia_check = await drush.run("acquia-deploy", ["--help"])
                if acquia_check.get("returncode") != 0:
                    return {
                        "error": "Neither acquia-cli nor Drush acquia integration available",
                        "hint": "Install acquia-cli: composer require acquia/cli or ensure Drush acquia commands are available",
                    }

                # Use legacy drush acquia-deploy
                deploy_result = await drush.run(
                    "acquia-deploy",
                    [
                        f"--site={site_id}",
                        f"--environment={environment}",
                        f"--branch={branch}",
                    ],
                )
                results["steps"].append({"step": "acquia_deploy", "result": deploy_result})

                if deploy_result.get("returncode") != 0:
                    results["error"] = "Acquia deploy failed"
                    return results

                # Run database updates via drush
                updb_result = await drush.run(
                    "acquia-command",
                    [
                        f"--site={site_id}",
                        f"--environment={environment}",
                        "drush updb -y",
                    ],
                )
                results["steps"].append({"step": "database_updates", "result": updb_result})

                # Clear cache
                cache_result = await drush.run(
                    "acquia-command",
                    [
                        f"--site={site_id}",
                        f"--environment={environment}",
                        "drush cr",
                    ],
                )
                results["steps"].append({"step": "cache_rebuild", "result": cache_result})

            results["success"] = all(
                step["result"].get("returncode", 0) == 0 for step in results["steps"]
            )
            return results

        except Exception as e:
            results["error"] = f"Acquia deploy failed: {str(e)}"
            results["hint"] = "Ensure acquia-cli is installed and authenticated, or Drush acquia integration is configured"
            return results

    @mcp.tool()
    async def backup_database(backup_path: str | None = None) -> dict[str, Any]:
        """Create database backup via Drush."""
        if not drush:
            return {"error": "Drush not available"}
        result = await drush.run(
            "sql-dump", ["--result-file=" + (backup_path or "/tmp/drupal-backup.sql")]
        )
        return {"returncode": result.get("returncode"), "path": backup_path}

    @mcp.tool()
    async def cache_rebuild() -> dict[str, Any]:
        """Clear and rebuild all Drupal caches via Drush."""
        if not drush:
            return {"error": "Drush not available"}
        result = await drush.run("cache-rebuild", [])
        return {"returncode": result.get("returncode"), "stdout": result.get("stdout"), "stderr": result.get("stderr")}
