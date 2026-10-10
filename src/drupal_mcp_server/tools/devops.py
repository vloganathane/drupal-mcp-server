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
    async def acquia_deploy(environment: str, branch: str = "main") -> dict:
        """Deploy to Acquia Cloud."""
        return {"environment": environment, "branch": branch, "status": "not_implemented"}

    @mcp.tool()
    async def backup_database(backup_path: str = None) -> dict:
        """Create database backup via Drush."""
        if not drush:
            return {"error": "Drush not available"}
        result = await drush.run("sql-dump", ["--result-file=" + (backup_path or "/tmp/drupal-backup.sql")])
        return {"returncode": result.get("returncode"), "path": backup_path}
