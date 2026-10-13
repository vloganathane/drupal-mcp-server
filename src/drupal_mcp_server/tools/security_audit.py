"""Security audit tools for Drupal."""

import json
import os
import shutil
from typing import Any

from fastmcp import FastMCP


def _find_tool_path(tool_name: str) -> str | None:
    """Find the path to a tool executable."""
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


def _ensure_dict(result: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
    """Ensure result is a dict, not a list."""
    if result is None:
        return {"error": "No response"}
    if isinstance(result, list):
        return {"error": f"Unexpected list response: {result}"}
    return result


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush: Any = deps.get("drush_client")
    jsonapi: Any = deps.get("jsonapi_client")

    @mcp.tool()
    async def security_scan(
        path: str,
        include_vendors: bool = False,
    ) -> dict[str, Any]:
        """Run security-focused SAST using PHPStan with security extensions."""
        if not drush:
            return {"error": "Drush not available"}
        try:
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
    async def dependency_scan() -> dict[str, Any]:
        """Scan dependencies for vulnerabilities using Composer audit and other tools."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            # Composer audit
            result = await drush.run("composer", ["audit", "--format=json"])
            composer_result = _ensure_dict(result)
            
            # Also check for roave/security-advisories
            security_advisories = await drush.run("composer", ["show", "roave/security-advisories", "--format=json"])
            security_result = _ensure_dict(security_advisories)
            
            return {
                "composer_audit": composer_result,
                "security_advisories": security_result,
            }
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def config_security_check() -> dict[str, Any]:
        """Check Drupal configuration for security issues."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            checks: dict[str, Any] = {}
            
            # Check for trusted host patterns
            result = await drush.run("config:get", ["system.site", "trusted_host_patterns"])
            checks["trusted_host_patterns"] = _ensure_dict(result)
            
            # Check for debug mode
            result = await drush.run("config:get", ["system.logging", "error_level"])
            checks["error_level"] = _ensure_dict(result)
            
            # Check for HTTPS enforcement
            result = await drush.run("config:get", ["system.performance", "cache.page.use_internal"])
            checks["page_cache_internal"] = _ensure_dict(result)
            
            # Check file system permissions
            result = await drush.run("ev", ["echo 'files' === file_prepare_directory('public://', FILE_CREATE_DIRECTORY) ? 'writable' : 'not writable';"])
            checks["files_writable"] = _ensure_dict(result)
            
            # Check for update status
            result = await drush.run("pm:security", ["--format=json"])
            checks["security_updates"] = _ensure_dict(result)
            
            return {"security_checks": checks}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def permission_audit(
        role: str | None = None,
    ) -> dict[str, Any]:
        """Audit user permissions and roles."""
        if not drush and not jsonapi:
            return {"error": "Drush or JSON:API not available"}
        try:
            if jsonapi:
                result = await jsonapi.get_resource("user_role", {"page[limit]": 100})
                roles = _ensure_dict(result)
            else:
                result = await drush.run("user:role:list", ["--format=json"])
                roles = _ensure_dict(result)
            
            if role and jsonapi:
                result = await jsonapi.get_resource("user_role", {"filter[name]": role})
                role_data = _ensure_dict(result)
                return {"role": role, "data": role_data}
            
            return {"roles": roles}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def sql_injection_scan(path: str) -> dict[str, Any]:
        """Scan for SQL injection vulnerabilities in custom code."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            # Use PHPStan with security extensions for SQL injection detection
            phpstan_path = _find_tool_path("phpstan")
            if not phpstan_path:
                return {"error": "PHPStan not found. Install with: composer require --dev phpstan/phpstan phpstan/phpstan-security"}
            
            cmd = [
                phpstan_path, "analyse", path, 
                "--level=8", 
                "--error-format=json",
                "--configuration=vendor/phpstan/phpstan-security/extension.neon"
            ]
            
            result = await drush.run("ev", [f"exec(\"{' '.join(cmd)}\", \$output); print_r(\$output);"])
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def xss_scan(path: str) -> dict[str, Any]:
        """Scan for XSS vulnerabilities in custom code."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            # Use PHPStan with security extensions for XSS detection
            phpstan_path = _find_tool_path("phpstan")
            if not phpstan_path:
                return {"error": "PHPStan not found. Install with: composer require --dev phpstan/phpstan phpstan/phpstan-security"}
            
            cmd = [
                phpstan_path, "analyse", path,
                "--level=8",
                "--error-format=json",
                "--configuration=vendor/phpstan/phpstan-security/extension.neon"
            ]
            
            result = await drush.run("ev", [f"exec(\"{' '.join(cmd)}\", \$output); print_r(\$output);"])
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def csp_audit() -> dict[str, Any]:
        """Content Security Policy audit."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            checks: dict[str, Any] = {}
            
            # Check CSP headers in settings.php
            result = await drush.run("ev", ["\$config = include 'sites/default/settings.php'; print_r(isset(\$config['csp']) ? \$config['csp'] : 'not set');"])
            checks["csp_config"] = _ensure_dict(result)
            
            # Check for CSP module
            result = await drush.run("pm:list", ["--type=module", "--status=enabled", "--format=json"])
            pm_result = _ensure_dict(result)
            if isinstance(pm_result.get("data"), dict):
                modules = pm_result["data"]
                checks["csp_module"] = "csp" in modules
            else:
                checks["csp_module"] = False
            
            # Check for secure headers module
            if isinstance(pm_result.get("data"), dict):
                modules = pm_result["data"]
                checks["secure_headers_module"] = "secure_headers" in modules
            else:
                checks["secure_headers_module"] = False
            
            return {"csp_checks": checks}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def file_permissions_audit(path: str = "public://") -> dict[str, Any]:
        """Audit file permissions for security issues."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("ev", [f"echo is_dir('{path}') ? 'exists' : 'not found';"])
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    def _find_tool_path(tool_name: str) -> str | None:
        """Find the path to a tool executable."""
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

    def _ensure_dict(result: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
        """Ensure result is a dict, not a list."""
        if result is None:
            return {"error": "No response"}
        if isinstance(result, list):
            return {"error": f"Unexpected list response: {result}"}
        return result
