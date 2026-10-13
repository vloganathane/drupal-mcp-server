"""Code audit/static analysis tools for Drupal."""

import os
import shutil
from typing import Any

from fastmcp import FastMCP


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")

    def _ensure_dict(result: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
        """Ensure result is a dict, not a list."""
        if result is None:
            return {"error": "No response"}
        if isinstance(result, list):
            return {"error": f"Unexpected list response: {result}"}
        return result

    def _find_tool_path(tool_name: str) -> str | None:
        """Find the path to a tool executable."""
        # Check common locations
        paths = [
            shutil.which(tool_name),
            f"/var/www/html/vendor/bin/{tool_name}",
            f"/app/vendor/bin/{tool_name}",
            f"./vendor/bin/{tool_name}",
        ]
        for path in paths:
            if path and os.path.exists(path):
                return path
        return None

    @mcp.tool()
    async def code_audit_phpstan(
        path: str,
        level: int = 5,
        configuration: str | None = None,
    ) -> dict[str, Any]:
        """Run PHPStan static analysis on Drupal custom modules."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            phpstan_path = _find_tool_path("phpstan")
            if not phpstan_path:
                return {"error": "PHPStan not found. Install with: composer require --dev phpstan/phpstan"}
            
            cmd = [phpstan_path, "analyse", path, f"--level={level}"]
            if configuration:
                cmd.extend(["-c", configuration])
            cmd.extend(["--error-format=json"])
            
            result = await drush.run("ev", [f"exec(\"{' '.join(cmd)}\", \$output); print_r(\$output);"])
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def drupal_check(
        path: str,
        severity: str = "error",
    ) -> dict[str, Any]:
        """Run Drupal Check for deprecated code detection."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            dcheck_path = _find_tool_path("drupal-check")
            if not dcheck_path:
                return {"error": "Drupal Check not found. Install with: composer require --dev mglaman/drupal-check"}
            
            cmd = [dcheck_path, path]
            if severity:
                cmd.extend(["--severity", severity])
            cmd.extend(["--format=json"])
            
            result = await drush.run("ev", [f"exec(\"{' '.join(cmd)}\", \$output); print_r(\$output);"])
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def code_sniffer(
        path: str,
        standard: str = "Drupal",
        severity: int = 5,
    ) -> dict[str, Any]:
        """Run PHP_CodeSniffer with Drupal coding standards."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            phpcs_path = _find_tool_path("phpcs")
            if not phpcs_path:
                return {"error": "PHP_CodeSniffer not found. Install with: composer require --dev squizlabs/php_codesniffer"}
            
            cmd = [phpcs_path, f"--standard={standard}", f"--severity={severity}", path, "--report=json"]
            
            result = await drush.run("ev", [f"exec(\"{' '.join(cmd)}\", \$output); print_r(\$output);"])
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def deprecation_scan(
        path: str,
        drupal_version: str = "10",
    ) -> dict[str, Any]:
        """Scan for deprecated Drupal API usage."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            # Use drupal-check for deprecation scanning
            dcheck_path = _find_tool_path("drupal-check")
            if not dcheck_path:
                return {"error": "Drupal Check not found. Install with: composer require --dev mglaman/drupal-check"}
            
            cmd = [dcheck_path, path, "--format=json"]
            
            result = await drush.run("ev", [f"exec(\"{' '.join(cmd)}\", \$output); print_r(\$output);"])
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def security_audit(
        path: str,
        include_vendors: bool = False,
    ) -> dict[str, Any]:
        """Run security-focused static analysis."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            # Use PHPStan with security extensions
            phpstan_path = _find_tool_path("phpstan")
            if not phpstan_path:
                return {"error": "PHPStan not found. Install with: composer require --dev phpstan/phpstan phpstan/phpstan-security"}
            
            cmd = [phpstan_path, "analyse", path, "--level=8", "--error-format=json"]
            if not include_vendors:
                cmd.extend(["--exclude=vendor"])
            
            result = await drush.run("ev", [f"exec(\"{' '.join(cmd)}\", \$output); print_r(\$output);"])
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def composer_audit() -> dict[str, Any]:
        """Run Composer security audit on dependencies."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("composer", ["audit", "--format=json"])
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def code_quality_report(
        path: str,
        tools: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run multiple code quality tools and generate combined report."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            available_tools = tools or ["phpstan", "drupal-check", "phpcs"]
            results = {}
            
            for tool in available_tools:
                try:
                    if tool == "phpstan":
                        result = await drush.run("ev", [f"exec(\"phpstan analyse {path} --error-format=json\", \$output); print_r(\$output);"])
                    elif tool == "drupal-check":
                        result = await drush.run("ev", [f"exec(\"drupal-check {path} --format=json\", \$output); print_r(\$output);"])
                    elif tool == "phpcs":
                        result = await drush.run("ev", [f"exec(\"phpcs --standard=Drupal {path} --report=json\", \$output); print_r(\$output);"])
                    else:
                        result = {"error": f"Unknown tool: {tool}"}
                    results[tool] = _ensure_dict(result)
                except Exception as e:
                    results[tool] = {"error": str(e)}
            
            return {"path": path, "results": results}
        except Exception as e:
            return {"error": str(e)}
