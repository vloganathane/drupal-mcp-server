"""DevOps tools for Drupal (Drush, DDEV, etc.)."""


def register_tools(mcp, **deps):
    drush = deps.get("drush_client")
    site_manager = deps.get("site_manager")

    @mcp.tool()
    async def drush_command(command: str, args: list = None, options: dict = None) -> dict:
        """Execute any Drush command."""
        if not drush:
            return {"error": "Drush not available"}
        cmd_args = args or []
        if options:
            for k, v in options.items():
                cmd_args.append(f"--{k}={v}" if v else f"--{k}")
        return await drush.run(command, cmd_args)

    @mcp.tool()
    async def ddev_setup(
        project_name: str = ".", drupal_version: str = "10", webroot: str = "web"
    ) -> dict:
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
    async def ddev_start(project_name: str = ".") -> dict:
        """Start DDEV project."""
        if not site_manager:
            return {"error": "Site manager not available"}
        return await site_manager.ddev_start()

    @mcp.tool()
    async def ddev_stop(project_name: str = ".") -> dict:
        """Stop DDEV project."""
        if not site_manager:
            return {"error": "Site manager not available"}
        return await site_manager.ddev_stop()

    @mcp.tool()
    async def ddev_exec(command: str, project_name: str = ".") -> dict:
        """Execute command in DDEV container."""
        if not site_manager:
            return {"error": "Site manager not available"}
        return await site_manager.ddev_exec(command)

    @mcp.tool()
    async def lando_start(project_name: str = ".") -> dict:
        """Start Lando project."""
        if not site_manager:
            return {"error": "Site manager not available"}
        return await site_manager.lando_start()

    @mcp.tool()
    async def lando_stop(project_name: str = ".") -> dict:
        """Stop Lando project."""
        if not site_manager:
            return {"error": "Site manager not available"}
        return await site_manager.lando_stop()

    @mcp.tool()
    async def lando_exec(command: str, project_name: str = ".") -> dict:
        """Execute command in Lando container."""
        if not site_manager:
            return {"error": "Site manager not available"}
        return await site_manager.lando_exec(command)

    @mcp.tool()
    async def lando_setup(
        project_name: str = ".", drupal_version: str = "10", webroot: str = "web"
    ) -> dict:
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
    async def acquia_deploy(environment: str, branch: str = "main", site_id: str = None) -> dict:
        """Deploy to Acquia Cloud via Drush (requires acquia-cli or Drush acquia integration)."""
        if not drush:
            return {"error": "Drush not available"}
        if not site_id:
            return {
                "error": "site_id required for Acquia deploy. Provide via Acquia Cloud Platform UI or DRUPAL_ACQUIA_SITE_ID env var."
            }
        # Check if acquia-cli is available via drush
        try:
            result = await drush.run(
                "acquia-deploy",
                ["--site=" + site_id, "--environment=" + environment, "--branch=" + branch],
            )
            return result
        except Exception as e:
            return {
                "error": f"Acquia deploy failed: {str(e)}",
                "hint": "Ensure acquia-cli is installed and authenticated",
            }

    @mcp.tool()
    async def backup_database(backup_path: str = None) -> dict:
        """Create database backup via Drush."""
        if not drush:
            return {"error": "Drush not available"}
        result = await drush.run(
            "sql-dump", ["--result-file=" + (backup_path or "/tmp/drupal-backup.sql")]
        )
        return {"returncode": result.get("returncode"), "path": backup_path}

    @mcp.tool()
    async def cache_rebuild() -> dict:
        """Clear and rebuild all Drupal caches via Drush."""
        if not drush:
            return {"error": "Drush not available"}
        result = await drush.run("cache-rebuild", [])
        return {"returncode": result.get("returncode"), "stdout": result.get("stdout"), "stderr": result.get("stderr")}
