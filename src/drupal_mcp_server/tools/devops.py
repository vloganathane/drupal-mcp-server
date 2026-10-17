"""DevOps tools for Drupal (Drush, DDEV, etc.)."""

import os
from typing import Any

from fastmcp import FastMCP

from ._utils import drush_result as _drush_result
from ._utils import ensure_dict as _ensure_dict
from ._utils import run_composer as _run_composer


def _existing_config_guard(config_path: str, force: bool) -> str | None:
    """Refuse to clobber a working site's config with a generated one."""
    if os.path.exists(config_path) and not force:
        return (
            f"{config_path} already exists. Writing a generated config over it "
            "would discard every setting you have. Edit the file directly, or "
            "pass force=True to replace it."
        )
    return None


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")
    site_manager = deps.get("site_manager")

    @mcp.tool()
    async def drush_command(command: str, args: list[str] | None = None, options: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute any Drush command.

        ``options`` values are rendered as drush expects them. Drush flags take
        no value, so ``{"yes": True}`` must become ``--yes`` and not
        ``--yes=True``, which drush rejects with "The --yes option does not
        accept a value". That made every confirmation-answering call fail --
        including ``pm:install``, so installing a module reported success
        while nothing was installed. A ``False`` means the caller does not want
        the flag, so it is omitted rather than spelled ``--yes=False``; that
        direction was the dangerous one, because it used to *pass* ``--yes``
        and silently suppress confirmation on destructive commands.
        """
        if not drush:
            return {"error": "Drush not available"}
        cmd_args = list(args or [])
        if options:
            for k, v in options.items():
                if v is None or v is False:
                    continue
                if v is True:
                    cmd_args.append(f"--{k}")
                else:
                    # Not `if v`: `--limit=0` and `--offset=0` are meaningful,
                    # and a falsy check turned them into bare `--limit`, which
                    # drush reads as a missing value.
                    cmd_args.append(f"--{k}={v}")
        return _ensure_dict(await drush.run(command, cmd_args))

    @mcp.tool()
    async def ddev_setup(
        project_name: str = ".",
        drupal_version: str = "10",
        docroot: str = "web",
        force: bool = False,
    ) -> dict[str, Any]:
        """Generate .ddev/config.yaml for a local Drupal environment.

        Refuses to overwrite an existing config: calling this with defaults on
        a working project used to replace the whole file with `name: .`, which
        takes the project down.
        """
        import re

        site_manager = deps.get("site_manager")
        if not site_manager:
            return {"error": "Site manager not available"}

        # Check for an existing config first: that is the message the caller
        # needs, whatever else is wrong with the arguments.
        config_path = os.path.join(project_name, ".ddev", "config.yaml")
        guarded = _existing_config_guard(config_path, force)
        if guarded:
            return {"error": guarded, "path": config_path, "project": project_name}

        name = os.path.basename(os.path.abspath(project_name))
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
            return {
                "error": (
                    f"{project_name!r} is not a usable DDEV project name. It "
                    "becomes the hostname, so it must be lowercase letters, "
                    "digits and hyphens only. Pass the project directory, for "
                    "example 'ddev_setup(\"my-site\")'."
                )
            }

        # DDEV 1.24 accepts `type:`, not `kind:`, and reads `docroot:`, not
        # `webroot:` - an unrecognised key is dropped, leaving an empty
        # docroot, so nginx serves the project root and every request 404s.
        ddev_config = f"""name: {name}
type: drupal{drupal_version}
docroot: {docroot}
"""
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
        """Start the DDEV project under ``project_name``.

        ``project_name`` is the project *directory* (default ``.``): DDEV
        resolves the project from the working directory it runs in, so this
        must be the directory containing ``.ddev``. Passing another project's
        path starts that project, not the server's own directory.
        """
        if not site_manager:
            return {"error": "Site manager not available"}
        return await site_manager.ddev_start(cwd=project_name)  # type: ignore[no-any-return]

    @mcp.tool()
    async def ddev_stop(project_name: str = ".") -> dict[str, Any]:
        """Stop the DDEV project under ``project_name`` (a directory)."""
        if not site_manager:
            return {"error": "Site manager not available"}
        return await site_manager.ddev_stop(cwd=project_name)  # type: ignore[no-any-return]

    @mcp.tool()
    async def ddev_exec(command: str, project_name: str = ".") -> dict[str, Any]:
        """Run ``command`` in the container of the DDEV project under
        ``project_name`` (a directory containing ``.ddev``)."""
        if not site_manager:
            return {"error": "Site manager not available"}
        return await site_manager.ddev_exec(command, cwd=project_name)  # type: ignore[no-any-return]

    @mcp.tool()
    async def lando_start(project_name: str = ".") -> dict[str, Any]:
        """Start the Lando project under ``project_name`` (a directory)."""
        if not site_manager:
            return {"error": "Site manager not available"}
        return await site_manager.lando_start(cwd=project_name)  # type: ignore[no-any-return]

    @mcp.tool()
    async def lando_stop(project_name: str = ".") -> dict[str, Any]:
        """Stop the Lando project under ``project_name`` (a directory)."""
        if not site_manager:
            return {"error": "Site manager not available"}
        return await site_manager.lando_stop(cwd=project_name)  # type: ignore[no-any-return]

    @mcp.tool()
    async def lando_exec(command: str, project_name: str = ".") -> dict[str, Any]:
        """Run ``command`` in the container of the Lando project under
        ``project_name`` (a directory)."""
        if not site_manager:
            return {"error": "Site manager not available"}
        return await site_manager.lando_exec(command, cwd=project_name)  # type: ignore[no-any-return]

    @mcp.tool()
    async def lando_setup(
        project_name: str = ".",
        drupal_version: str = "10",
        webroot: str = "web",
        force: bool = False,
    ) -> dict[str, Any]:
        """Generate .lando.yml for a local Drupal environment."""
        if not site_manager:
            return {"error": "Site manager not available"}

        name = os.path.basename(os.path.abspath(project_name))
        config_path = os.path.join(project_name, ".lando.yml")
        guarded = _existing_config_guard(config_path, force)
        if guarded:
            return {"error": guarded, "path": config_path, "project": project_name}

        lando_config = f"""name: {name}
recipe: drupal{drupal_version}
webroot: {webroot}
"""
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
        destination = backup_path or "/tmp/drupal-backup.sql"
        result = await drush.run("sql-dump", ["--result-file=" + destination])
        return _drush_result(result, path=destination)

    @mcp.tool()
    async def cache_rebuild() -> dict[str, Any]:
        """Clear and rebuild all Drupal caches via Drush."""
        if not drush:
            return {"error": "Drush not available"}
        result = await drush.run("cache-rebuild", [])
        return _drush_result(result)

    @mcp.tool()
    async def composer_install(
        working_dir: str = ".",
        no_dev: bool = False,
        optimize: bool = True,
    ) -> dict[str, Any]:
        """Run composer install."""
        try:
            args = ["install", "--working-dir=" + working_dir]
            if no_dev:
                args.append("--no-dev")
            if optimize:
                args.append("--optimize-autoloader")
            return await _run_composer(args)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def composer_require(
        package: str,
        version: str | None = None,
        dev: bool = False,
        working_dir: str = ".",
    ) -> dict[str, Any]:
        """Require one or more packages via composer.

        Several packages may be given at once, space separated, the way
        `composer require` itself accepts them. They used to arrive as a single
        argv token, so composer read "drupal/pathauto" as a version constraint
        on "drupal/token" and refused the command with "Could not parse version
        constraint" -- a confusing error for the ordinary request "install
        these two modules". A package name never contains a space, so the
        split is unambiguous.
        """
        try:
            packages = str(package).split()
            if not packages:
                return {"error": "No package given."}
            # A version only makes sense against a single package; applying it
            # to each one in a list would silently pin all of them the same.
            if version and len(packages) == 1:
                packages = [f"{packages[0]}:{version}"]
            args = ["require", *packages]
            if dev:
                args.append("--dev")
            args.append("--working-dir=" + working_dir)
            return await _run_composer(args)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def composer_update(
        working_dir: str = ".",
        no_dev: bool = False,
    ) -> dict[str, Any]:
        """Run composer update."""
        try:
            args = ["update"]
            if no_dev:
                args.append("--no-dev")
            args.append("--working-dir=" + working_dir)
            return await _run_composer(args)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def drush_cron() -> dict[str, Any]:
        """Run cron."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("cron")
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def drush_watchdog(
        count: int = 50,
        type_filter: str | None = None,
        severity: str | None = None,
    ) -> dict[str, Any]:
        """Show recent log entries from watchdog."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            args = [f"--count={count}"]
            if type_filter:
                args.append(f"--type={type_filter}")
            if severity:
                args.append(f"--severity={severity}")
            result = await drush.run("watchdog:show", args)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def cache_clear(bins: list[str] | None = None) -> dict[str, Any]:
        """Clear specific cache bins."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            if bins:
                results = {}
                for bin_name in bins:
                    result = await drush.run("cache:clear", [bin_name])
                    results[bin_name] = _ensure_dict(result)
                return {"bins_cleared": results}
            else:
                # Clear all caches
                result = await drush.run("cache:rebuild", [])
                return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def drush_updb() -> dict[str, Any]:
        """Run database updates."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("updatedb", ["-y"])
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def drush_php_eval(code: str) -> dict[str, Any]:
        """Execute arbitrary PHP code via Drush."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("php:eval", [code])
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}
