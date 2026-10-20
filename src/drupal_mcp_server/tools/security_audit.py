"""Security audit tools for Drupal."""

import asyncio
import json
import os
import re
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml
from fastmcp import FastMCP

from ..config import get_settings
from ..validation import validate_identifier
from ._utils import ensure_dict as _ensure_dict
from ._utils import php_single_quote as _php_quote
from ._utils import run_composer as _run_composer


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


async def _proc_run(cmd: list[str]) -> dict[str, Any]:
    """Run a process safely without shell interpolation."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    try:
        data = json.loads(stdout.decode()) if stdout else {}
    except json.JSONDecodeError:
        data = {"output": stdout.decode()}
    return {
        "returncode": proc.returncode,
        "data": data,
        "stderr": stderr.decode(),
        "command": " ".join(cmd),
    }


async def _phpstan_help(path: str) -> str:
    """Ask this PHPStan build what it supports.

    --exclude-path only exists from PHPStan 1.0 onwards; older builds accept
    neither it nor --exclude and reject the whole run.
    """
    try:
        result = await _proc_run([path, "analyse", "--help"])
    except Exception:
        return ""
    return f"{result.get('stderr', '')}{result.get('data', {}).get('output', '')}"


def _vendor_exclude_args(help_text: str) -> list[str]:
    return ["--exclude-path=#/vendor/#"] if "--exclude-path" in help_text else []


# ---------------------------------------------------------------------------
# Local pattern scanner (Wave 5, ported from drupal-scout-mcp's security
# engine). Zero dependencies: PHP/JS/Drupal-template files are matched
# against a curated regex registry with Drupal-aware false-positive rules,
# so a site without PHPStan still gets concrete findings. The optional
# tree-sitter AST layer scout layers on top was not ported — the pattern
# pass is what carries the signal.
# ---------------------------------------------------------------------------

# Category key -> pattern name -> detection. Patterns, severities, and
# remediation text follow scout's registry (MIT); two corrections were
# made: `t(` is not a Drupal 7 leftover (it is alive in D8+ and flagged
# every translation call), and scout's CSRF pattern escaped `$request`
# as `\\$request`, which matches a literal backslash and never PHP.
SECURITY_PATTERNS: dict[str, dict[str, dict[str, str]]] = {
    "xss": {
        "unescaped_print": {
            "pattern": r"\b(print|echo)\s+\$",
            "severity": "high",
            "description": "Direct output of variable without escaping",
            "recommendation": "Use \\Drupal\\Component\\Utility\\Html::escape() or render arrays with #markup",
        },
        "unsafe_render_string": {
            "pattern": r"['\"](#[\w_]+)['\"]:\s*\$[\w_]+(?!\s*[,\]])",
            "severity": "medium",
            "description": "Variable assigned to render array without explicit sanitization",
            "recommendation": "Use #markup with Xss::filterAdmin() or #plain_text for user content",
        },
        "drupal_set_message_var": {
            "pattern": r"drupal_set_message\(\s*\$",
            "severity": "medium",
            "description": "drupal_set_message() with variable (potential XSS)",
            "recommendation": "Use t() or Markup::create() to sanitize",
        },
        "direct_superglobal": {
            "pattern": r"\b(echo|print|return)\s+.*\$_(GET|POST|REQUEST|COOKIE)",
            "severity": "high",
            "description": "Direct output of user input from superglobals",
            "recommendation": "Use \\Drupal\\Component\\Utility\\Html::escape() or Xss::filter()",
        },
        "javascript_innerhtml": {
            "pattern": r"\.innerHTML\s*=|\.outerHTML\s*=",
            "severity": "medium",
            "description": "Direct DOM manipulation (XSS vector in JavaScript)",
            "recommendation": "Use textContent or sanitize with DOMPurify",
        },
    },
    "sql_injection": {
        "db_query_concat": {
            "pattern": r"db_query\([^)]*\.\s*\$|db_query\([^)]*%[sd].*,\s*\$_",
            "severity": "high",
            "description": "db_query() with string concatenation or direct superglobals",
            "recommendation": "Use placeholders: db_query('SELECT ... WHERE id = :id', [':id' => $id])",
        },
        "sql_concat": {
            "pattern": r"['\"](\s*SELECT\s+|\s*INSERT\s+INTO\s+|\s*UPDATE\s+|\s*DELETE\s+FROM\s+).*['\"]?\s*\.\s*\$",
            "severity": "high",
            "description": "SQL query string with variable concatenation",
            "recommendation": "Use Drupal's Database API with placeholders",
        },
        "mysqli_query_concat": {
            "pattern": r"(mysqli_query|mysql_query|->query)\([^)]*['\"].*\.\s*\$",
            "severity": "high",
            "description": "Direct database query with concatenation",
            "recommendation": "Use prepared statements or Drupal's Database API",
        },
        "entity_query_user_input": {
            "pattern": r"->condition\([^)]*\$_(GET|POST|REQUEST)",
            "severity": "medium",
            "description": "EntityQuery condition with direct user input",
            "recommendation": "Validate and sanitize user input before EntityQuery",
        },
    },
    "command_injection": {
        "exec_with_variable": {
            "pattern": r"\b(exec|shell_exec|system|passthru|proc_open|popen)\s*\([^)]*\$",
            "severity": "high",
            "description": "Command execution function with variable (potential command injection)",
            "recommendation": "Avoid shell commands. Use PHP functions or escapeshellarg()/escapeshellcmd()",
        },
        "backtick_operator": {
            "pattern": r"`[^`]*\$[^`]*`",
            "severity": "high",
            "description": "Backtick shell execution with variable (command injection risk)",
            "recommendation": "Avoid backtick operator. Use PHP functions instead",
        },
        "drush_shell_exec": {
            "pattern": r"drush_shell_exec\([^)]*\$",
            "severity": "high",
            "description": "Drush shell execution with variable",
            "recommendation": "Use Drush API directly instead of shell commands",
        },
        "mail_injection": {
            "pattern": r"\bmail\s*\([^)]*\$_(GET|POST|REQUEST)",
            "severity": "medium",
            "description": "mail() with user input (potential header/command injection)",
            "recommendation": "Use Drupal's mail system and sanitize inputs",
        },
    },
    "path_traversal": {
        "file_include_variable": {
            "pattern": r"\b(include|require|include_once|require_once)\s*\([^)]*\$_(GET|POST|REQUEST|COOKIE)",
            "severity": "high",
            "description": "File include with user input (path traversal/RCE risk)",
            "recommendation": "Never include files based on user input. Use whitelist approach",
        },
        "file_read_variable": {
            "pattern": r"\b(file_get_contents|fopen|readfile|file)\s*\([^)]*\$_(GET|POST|REQUEST)",
            "severity": "high",
            "description": "File read operation with user input (path traversal risk)",
            "recommendation": "Validate with realpath(), check against allowed directories",
        },
        "dotdot_slash": {
            "pattern": r"\$[^=]*\.\.[\\/]",
            "severity": "medium",
            "description": "Potential path traversal sequence (../) in variable",
            "recommendation": "Use realpath() or drupal_realpath() to canonicalize paths",
        },
        "drupal_file_ops_no_validation": {
            "pattern": r"file_save_data\([^)]*\$_(GET|POST)|->createFile\([^)]*\$_(GET|POST)",
            "severity": "medium",
            "description": "File operation with user input without visible validation",
            "recommendation": "Validate filename, use file_munge_filename(), check directory permissions",
        },
        "file_delete_user_input": {
            "pattern": r"\b(unlink|file_unmanaged_delete)\s*\([^)]*\$_(GET|POST|REQUEST)",
            "severity": "high",
            "description": "File deletion with user input (path traversal risk)",
            "recommendation": "Validate against allowed directories, use realpath()",
        },
    },
    "hardcoded_secrets": {
        "api_key_hardcoded": {
            "pattern": r"['\"]?api[_-]?key['\"]?\s*[=:]\s*['\"][a-zA-Z0-9_\-]{16,}['\"]",
            "severity": "high",
            "description": "Hardcoded API key detected",
            "recommendation": "Use settings.php, environment variables, or Key module",
        },
        "password_hardcoded": {
            "pattern": r"['\"]?password['\"]?\s*[=:]\s*['\"][^'\"]{8,}['\"]",
            "severity": "high",
            "description": "Hardcoded password detected",
            "recommendation": "Never hardcode passwords. Use configuration or Key module",
        },
        "db_credentials": {
            "pattern": r"['\"](mysql|mysqli|pdo):.*password[=:][^;'\"]+",
            "severity": "high",
            "description": "Database credentials in code",
            "recommendation": "Use settings.php for database configuration",
        },
        "private_key_hardcoded": {
            "pattern": r"['\"]?(private|secret)[_-]?key['\"]?\s*[=:]\s*['\"][a-zA-Z0-9+/=]{20,}['\"]",
            "severity": "high",
            "description": "Hardcoded private/secret key detected",
            "recommendation": "Use Key module or settings.php",
        },
        "oauth_token_hardcoded": {
            "pattern": r"['\"]?(access|bearer|oauth)[_-]?token['\"]?\s*[=:]\s*['\"][a-zA-Z0-9_\-\.]{20,}['\"]",
            "severity": "high",
            "description": "Hardcoded OAuth/access token detected",
            "recommendation": "Use secure credential storage (Key module, settings.php)",
        },
        "aws_key_pattern": {
            "pattern": r"(AKIA[0-9A-Z]{16}|aws[_-]?secret|aws[_-]?access)",
            "severity": "high",
            "description": "AWS credentials pattern detected",
            "recommendation": "Use IAM roles or AWS credentials file, not hardcoded keys",
        },
    },
    "access_control": {
        "form_no_access": {
            "pattern": r"class\s+\w+\s+extends\s+FormBase",
            "severity": "medium",
            "description": "Form class declared - verify an access() method or route _permission exists",
            "recommendation": "Implement access() method or use _permission in routing",
        },
        "missing_permission_check": {
            "pattern": r"(->save\(\)|->delete\(\)|->update\(\))(?!.*->access\()",
            "severity": "medium",
            "description": "Entity modification without visible access check",
            "recommendation": "Use ->access('update'/'delete') before operations",
        },
        "user_load_no_check": {
            "pattern": r"User::load\(|user_load\(",
            "severity": "low",
            "description": "User entity loaded without access verification",
            "recommendation": "Use ->access('view') after loading sensitive user data",
        },
    },
    "csrf": {
        "custom_post_no_csrf": {
            "pattern": r"Request::(create|createFromGlobals)|\$request->request->get\(.*\$_POST",
            "severity": "medium",
            "description": "Custom POST handler detected - verify CSRF token validation is present",
            "recommendation": "Use Form API (auto CSRF) or validate with \\Drupal::csrfToken()->validate()",
        },
        "potential_get_state_change": {
            "pattern": r"(->save\(\)|->delete\(\)|->update\(\)|->create\(\))",
            "severity": "low",
            "description": "State-changing operation detected - verify route uses POST/DELETE with CSRF",
            "recommendation": "Ensure operation is in POST route with Form API or CSRF token",
        },
    },
    "deprecated_api": {
        "drupal7_functions": {
            "pattern": r"\b(drupal_set_message|drupal_get_path|drupal_goto|variable_get|variable_set|db_query|db_select|format_date)\(",
            "severity": "medium",
            "description": "Drupal 7 function used (deprecated in D8+)",
            "recommendation": "Use D8+ services: \\Drupal::messenger(), \\Drupal::database(), etc.",
        },
        "eval_usage": {
            "pattern": r"\beval\s*\(",
            "severity": "high",
            "description": "eval() usage detected (security risk)",
            "recommendation": "Refactor to avoid eval() - use proper PHP constructs",
        },
        "unserialize_user_input": {
            "pattern": r"unserialize\([^)]*\$_(GET|POST|REQUEST|COOKIE)",
            "severity": "high",
            "description": "unserialize() with user input (RCE risk)",
            "recommendation": "Use JSON or validate source before unserialize()",
        },
        "create_function": {
            "pattern": r"\bcreate_function\s*\(",
            "severity": "medium",
            "description": "create_function() is deprecated (removed in PHP 8)",
            "recommendation": "Use anonymous functions: function() { ... }",
        },
        "extract_usage": {
            "pattern": r"\bextract\s*\(",
            "severity": "medium",
            "description": "extract() can overwrite variables (security/maintainability risk)",
            "recommendation": "Manually assign array values to avoid variable pollution",
        },
        "assert_string": {
            "pattern": r"\bassert\s*\(['\"]",
            "severity": "high",
            "description": "assert() with string is deprecated and dangerous (removed in PHP 8)",
            "recommendation": "Use proper conditionals or assertions with boolean expressions",
        },
    },
}

_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
_SEVERITIES = frozenset(_SEVERITY_RANK)
# Drupal code files worth scanning; templates and JS carry XSS vectors.
_SCAN_SUFFIXES = (".php", ".module", ".install", ".inc", ".profile", ".theme", ".engine", ".js")
# Never walked: dependencies, builds, and the scanner's own noise centers.
# "contrib" is pruned too so the default target scans the site's own code;
# an explicit module=name walk starts inside that module, past this segment.
_SKIP_SCAN_DIRS = frozenset(
    {"node_modules", "vendor", ".git", ".yarn", "tests", "test", "dist", "build", "contrib"}
)
_MAX_SCAN_FILES = 5000
_MAX_SCAN_LINES = 20_000
_MAX_LINE_CHARS = 2_000
_SNIPPET_CAP = 200
_MAX_ROUTE_FILES = 200
_MAX_ROUTES = 500


def _compiled_patterns(
    categories: list[str] | None, severity: str | None
) -> list[tuple[str, str, re.Pattern[str], dict[str, str]]]:
    """The (category, name, regex, spec) tuples a scan will run."""
    chosen = categories if categories else sorted(SECURITY_PATTERNS)
    compiled: list[tuple[str, str, re.Pattern[str], dict[str, str]]] = []
    for category in chosen:
        for name, spec in SECURITY_PATTERNS[category].items():
            if severity and spec["severity"] != severity:
                continue
            compiled.append((category, name, re.compile(spec["pattern"]), spec))
    return compiled


def _is_false_positive(line: str, category: str, pattern_name: str, filename: str) -> bool:
    """Drupal-aware context that turns a regex hit into a non-finding.

    EntityQuery, TempStore, Config, State, and Cache calls look like SQL
    to a regex but are safe; escapeshellarg and stream wrappers likewise.
    Ported from scout's filter table, plus two rules the live site
    proved necessary: JS template literals are not shell backticks, and
    Drupal's '{table}' / ->...Table() concatenation names tables rather
    than carrying user data.
    """
    lowered = line.lower()

    if category == "sql_injection":
        safe_apis = (
            "->condition(", "->fields(", "->range(", "->sort(",
            "gettempstore(", "getprivatetempstore(", "getsharedtempstore(",
            "->get(", "->set(", "->delete(",
            "cache_get(", "cache_set(", "state_get(", "config_get(",
        )
        if any(api in lowered for api in safe_apis):
            return True
        if pattern_name == "sql_concat" and not any(
            fn in lowered for fn in ("db_query", "->query(", "mysqli", "pdo")
        ):
            return True
        if not re.search(r"\$_(GET|POST|REQUEST|COOKIE)", line) and (
            re.search(r"FROM\s*\{", line) or re.search(r"\$this->\w*Table\w*\(", line)
        ):
            # '{table}' fragments and $this->...Table() getters are
            # Drupal's table-prefix idiom; the placeholders they carry
            # mean the values are bound, not concatenated.
            return True

    if category == "access_control" and pattern_name == "missing_permission_check":
        if any(kw in lowered for kw in ("config->save(", "cache->delete(", "state->delete(")):
            return True

    if category == "command_injection":
        if "escapeshellarg" in lowered or "escapeshellcmd" in lowered:
            return True
        if pattern_name == "drush_shell_exec" and "$" not in line:
            return True
        if pattern_name == "backtick_operator" and filename.endswith(".js"):
            # JavaScript backticks are template literals; that language
            # has no shell-execution backticks at all.
            return True

    if category == "path_traversal":
        if "realpath(" in lowered or "drupal_realpath(" in lowered:
            return True
        if "file_create_url" in lowered:
            return True
        if any(wrapper in line for wrapper in ("public://", "private://", "temporary://")):
            return True

    if category == "hardcoded_secrets":
        if any(word in lowered for word in ("example", "placeholder", "your_api_key", "your_password", "xxx")):
            return True
        if "phpunit" in lowered or "test.php" in lowered:
            return True
        if line.strip().startswith(("//", "#", "*", "/*")):
            return True

    if category == "xss":
        if "drupal_set_message" in lowered and "t(" in lowered:
            return True
        if pattern_name == "unsafe_render_string" and "return $" in lowered:
            # Form/build/element/requirements returns are Form API or render
            # arrays: sanitization happens downstream.
            return True

    return False


def _drupal_root() -> str | None:
    """Configured Drupal root, or None when the server does not know one."""
    try:
        return get_settings().DRUPAL_ROOT
    except Exception:
        return None


def _inside_root(root: str, relative: str) -> Path | None:
    """Resolve ``relative`` under the docroot, or None if it escapes."""
    if not relative or Path(relative).is_absolute():
        return None
    base = Path(root)
    try:
        resolved = (base / relative).resolve()
        root_resolved = base.resolve()
    except OSError:
        return None
    if resolved == root_resolved or resolved.is_relative_to(root_resolved):
        return resolved
    return None


def _module_dir(root: str, name: str) -> Path | None:
    """Locate a module directory anywhere a Drupal project keeps modules."""
    base = Path(root)
    candidates = [
        f"modules/{name}",
        f"modules/custom/{name}",
        f"modules/contrib/{name}",
        f"web/modules/{name}",
        f"web/modules/custom/{name}",
        f"web/modules/contrib/{name}",
        f"core/modules/{name}",
    ]
    for sites in (base / "sites", base / "web" / "sites"):
        if sites.is_dir():
            for site_dir in sorted(sites.glob("*")):
                candidates.append(str(site_dir / "modules" / name))
    for relative in candidates:
        resolved = _inside_root(root, relative)
        if resolved is not None and resolved.is_dir():
            return resolved
    return None


def _default_scan_targets(root: str) -> list[Path]:
    """The site's own code: modules and themes outside contrib and core."""
    base = Path(root)
    targets: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        if path.is_dir() and path.resolve() not in seen:
            seen.add(path.resolve())
            targets.append(path.resolve())

    for relative in ("modules", "web/modules", "themes", "web/themes"):
        add(base / relative)
    for sites in (base / "sites", base / "web" / "sites"):
        if sites.is_dir():
            for site_dir in sorted(sites.glob("*")):
                add(site_dir / "modules")
                add(site_dir / "themes")
    return targets


def _iter_code_files(target: Path, root: Path) -> Iterator[tuple[Path, str]]:
    """Pruned walk yielding (path, relative-to-docroot) for scannable files.

    Symlinks are skipped outright — a link out of the docroot must not
    pull outside content into a security report.
    """
    for dirpath, dirnames, filenames in os.walk(target):
        current = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_SCAN_DIRS)
        for filename in sorted(filenames):
            lower = filename.lower()
            if not lower.endswith(_SCAN_SUFFIXES) or lower.endswith(".min.js"):
                continue
            path = current / filename
            if path.is_symlink():
                continue
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if not resolved.is_relative_to(root):
                continue
            yield path, str(path.relative_to(root))


def _resolve_scan_target(
    root: str, module: str | None, path: str | None
) -> tuple[list[Path], dict[str, Any] | None]:
    """``(directories, error)`` for one of the two scan tools."""
    if module and path:
        return [], {"error": "Pass either module or path, not both"}
    if module:
        invalid = validate_identifier(module, "module")
        if invalid is not None:
            return [], {"error": invalid}
        directory = _module_dir(root, module)
        if directory is None:
            return [], {
                "error": (
                    f"Module {module!r} not found under modules/, web/modules/, "
                    "sites/*/modules, or core/modules"
                )
            }
        return [directory], None
    if path:
        directory = _inside_root(root, path)
        if directory is None or not directory.is_dir():
            return [], {
                "error": (
                    f"Path {path!r} is not a directory inside DRUPAL_ROOT ({root})"
                )
            }
        return [directory], None
    targets = _default_scan_targets(root)
    if not targets:
        return [], {"error": f"No modules/ or themes/ directories under DRUPAL_ROOT ({root})"}
    return targets, None


def _class_index(targets: list[Path], root: Path) -> dict[str, str]:
    """Map PHP class name -> docroot-relative file, for route controllers."""
    class_re = re.compile(r"^\s*(?:final\s+|abstract\s+)?class\s+(\w+)", re.M)
    index: dict[str, str] = {}
    for target in targets:
        for path, relative in _iter_code_files(target, root):
            if path.suffix.lower() not in (".php", ".module", ".inc"):
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for match in class_re.finditer(content):
                index.setdefault(match.group(1), relative)
    return index


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
                cmd.extend(_vendor_exclude_args(await _phpstan_help(phpstan_path)))
            
            result = await _proc_run(cmd)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def dependency_scan() -> dict[str, Any]:
        """Scan dependencies for vulnerabilities using Composer audit and other tools."""
        # No drush client needed: drush has no `composer` command (the
        # run_composer docstring records the same lesson), so every call
        # died with `Command "composer" is not defined` while the wrapped
        # result still answered "OK" to the sweep. Composer is its own
        # executable -- run_composer finds it, or the container's copy.
        try:
            composer_result = await _run_composer(["audit", "--format=json"])
            security_result = await _run_composer(["show", "roave/security-advisories"])

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
                # Drush 13 renamed this; `user:role:list` is not a command.
                result = await drush.run("role:list")
                roles = _ensure_dict(result)
            
            if role and jsonapi:
                # user_role exposes `label`, not `name`. Filtering on `name`
                # returned 400 "Invalid nested filtering ... the field `name`
                # does not exist" every time, so this branch never worked.
                result = await jsonapi.get_resource("user_role", {"filter[label]": role})
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
            
            result = await _proc_run(cmd)
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

            result = await _proc_run(cmd)
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
            result = await drush.run("ev", ["\\$config = include 'sites/default/settings.php'; print_r(isset(\\$config['csp']) ? \\$config['csp'] : 'not set');"])
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
            # Validate path to prevent injection
            allowed_prefixes = ('public://', 'private://', 'temporary://')
            prefix = next((p for p in allowed_prefixes if path.startswith(p)), None)
            if prefix is None:
                return {"error": f"Invalid path. Must start with one of: {allowed_prefixes}"}
            # The prefix allowlist alone left the suffix injectable: the
            # whole path was spliced into a PHP single-quoted literal, so
            # `public://x'); system('id'); //` passed the prefix check and
            # became code. Only a conservative charset survives the splice.
            suffix = path[len(prefix):]
            if not re.fullmatch(r"[A-Za-z0-9_./\-]*", suffix):
                return {
                    "error": (
                        "path may only contain letters, digits, and _ . / - "
                        f"after the stream prefix; got {path!r}"
                    )
                }
            code = f"echo is_dir({_php_quote(path)}) ? 'exists' : 'not found';"
            result = await drush.run("ev", [code])
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def code_security_scan(
        module: str | None = None,
        path: str | None = None,
        categories: list[str] | None = None,
        severity: str | None = None,
        max_findings: int = 50,
    ) -> dict[str, Any]:
        """Scan custom code for vulnerability patterns — no tools to install.

        Matches PHP/JS/Drupal files against a curated registry of XSS,
        SQL injection, command injection, path traversal, hardcoded
        secrets, access-control, CSRF, and deprecated-API patterns, with
        Drupal-aware false-positive rules (EntityQuery conditions, stream
        wrappers, escapeshellarg, and similar safe APIs are recognized).
        The counterpart of security_scan, which needs PHPStan installed.

        Target one module by machine name, or a directory relative to
        DRUPAL_ROOT; with neither, the site's own modules/ and themes/
        directories are scanned (contrib and core excluded). categories
        narrows to registry keys ('xss', 'sql_injection',
        'command_injection', 'path_traversal', 'hardcoded_secrets',
        'access_control', 'csrf', 'deprecated_api'); severity narrows to
        one level. Findings carry file, line, snippet, and a fix
        recommendation; counts cover the full run even when max_findings
        truncates the list.
        """
        if module and path:
            return {"error": "Pass either module or path, not both"}
        if categories is not None:
            if not isinstance(categories, list) or not categories:
                return {"error": "categories must be a non-empty list of registry keys"}
            unknown = [c for c in categories if c not in SECURITY_PATTERNS]
            if unknown:
                return {
                    "error": f"Unknown categories: {unknown}",
                    "available": sorted(SECURITY_PATTERNS),
                }
        if severity is not None and severity not in _SEVERITIES:
            return {"error": f"severity must be one of {sorted(_SEVERITIES)}"}
        if not isinstance(max_findings, int) or not 1 <= max_findings <= 500:
            return {"error": "max_findings must be an integer between 1 and 500"}
        root = _drupal_root()
        if not root:
            return {"error": "DRUPAL_ROOT must point at a local Drupal docroot to scan files"}
        targets, error = _resolve_scan_target(root, module, path)
        if error:
            return error

        compiled = _compiled_patterns(categories, severity)
        root_path = Path(root).resolve()
        findings: list[dict[str, Any]] = []
        files_scanned = 0
        filtered = 0
        truncated_files = False
        for target in targets:
            for file_path, relative in _iter_code_files(target, root_path):
                files_scanned += 1
                try:
                    raw = file_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for lineno, line in enumerate(raw.splitlines()[:_MAX_SCAN_LINES], start=1):
                    if len(line) > _MAX_LINE_CHARS:
                        line = line[:_MAX_LINE_CHARS]
                    for category, name, regex, spec in compiled:
                        if not regex.search(line):
                            continue
                        if _is_false_positive(line, category, name, relative):
                            filtered += 1
                            continue
                        findings.append(
                            {
                                "file": relative,
                                "line": lineno,
                                "category": category,
                                "pattern": name,
                                "severity": spec["severity"],
                                "description": spec["description"],
                                "recommendation": spec["recommendation"],
                                "snippet": line.strip()[:_SNIPPET_CAP],
                            }
                        )
                if files_scanned >= _MAX_SCAN_FILES:
                    truncated_files = True
                    break
            if truncated_files:
                break

        by_category: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        for finding in findings:
            by_category[finding["category"]] = by_category.get(finding["category"], 0) + 1
            by_severity[finding["severity"]] = by_severity.get(finding["severity"], 0) + 1
        findings.sort(
            key=lambda row: (
                _SEVERITY_RANK.get(str(row["severity"]), 9),
                str(row["file"]),
                int(row["line"]),
            )
        )
        payload: dict[str, Any] = {
            "target": {"module": module, "path": path},
            "files_scanned": files_scanned,
            "findings": findings[:max_findings],
            "counts": {"by_category": by_category, "by_severity": by_severity},
            "false_positives_filtered": filtered,
            "truncated": truncated_files or len(findings) > max_findings,
            "max_findings": max_findings,
        }
        if not files_scanned:
            payload["note"] = (
                "No scannable files in the target; nothing was verified. "
                "Point module or path at directories that hold code."
            )
        elif not findings:
            payload["note"] = "No pattern matches in the scanned files."
        elif len(findings) > max_findings:
            payload["note"] = (
                f"{len(findings)} findings total; the first {max_findings} "
                "(highest severity) are shown."
            )
        if truncated_files:
            payload["note"] = (
                f"Stopped after {_MAX_SCAN_FILES} files; narrow the target or "
                "use categories to finish the review."
            )
        return payload

    @mcp.tool()
    async def route_access_audit(
        module: str | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Classify every route's access control from *.routing.yml files.

        The routing half of a pre-deployment review: each route is
        classified by what it requires — fully anonymous (`access: TRUE`),
        a permission, roles, entity access, a custom access callback, or
        nothing at all, which is the finding. Controllers are mapped to
        the file that declares the class when it can be found, so a risky
        route leads straight to code. Targets work like
        code_security_scan: one module by machine name, a DRUPAL_ROOT
        directory, or the site's own modules/ and themes/ by default.
        """
        if module and path:
            return {"error": "Pass either module or path, not both"}
        root = _drupal_root()
        if not root:
            return {
                "error": "DRUPAL_ROOT must point at a local Drupal docroot to read routing files"
            }
        targets, error = _resolve_scan_target(root, module, path)
        if error:
            return error

        root_path = Path(root).resolve()
        classes = _class_index(targets, root_path)
        routes: list[dict[str, Any]] = []
        route_files = 0
        parse_errors: list[str] = []
        for target in targets:
            for dirpath, dirnames, filenames in os.walk(target):
                current = Path(dirpath)
                dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_SCAN_DIRS)
                for filename in sorted(filenames):
                    if not filename.endswith(".routing.yml"):
                        continue
                    route_files += 1
                    file_path = current / filename
                    if file_path.is_symlink():
                        continue
                    try:
                        resolved = file_path.resolve()
                    except OSError:
                        continue
                    if not resolved.is_relative_to(root_path):
                        continue
                    try:
                        data = yaml.safe_load(
                            file_path.read_text(encoding="utf-8", errors="replace")
                        )
                    except (OSError, yaml.YAMLError) as exc:
                        parse_errors.append(f"{filename}: {exc}")
                        continue
                    if not isinstance(data, dict):
                        continue
                    relative = str(file_path.relative_to(root_path))
                    for name, definition in data.items():
                        if not isinstance(definition, dict):
                            continue
                        defaults = definition.get("defaults") or {}
                        requirements = definition.get("requirements") or {}
                        defaults = defaults if isinstance(defaults, dict) else {}
                        requirements = requirements if isinstance(requirements, dict) else {}
                        controller = defaults.get("_controller") or defaults.get("_form")
                        access_flag = str(definition.get("access") or "").upper()
                        alias = definition.get("alias")
                        entity_form = defaults.get("_entity_form")
                        if access_flag == "TRUE":
                            kind = "anonymous"
                        elif access_flag == "FALSE":
                            kind = "denied"
                        elif "_permission" in requirements:
                            kind = f"permission:{requirements['_permission']}"
                        elif "_role" in requirements:
                            kind = f"role:{requirements['_role']}"
                        elif "_entity_access" in requirements:
                            kind = "entity"
                        elif "_custom_access" in requirements:
                            kind = "custom"
                        elif any(key.startswith("_") for key in requirements):
                            # An access requirement this classifier doesn't
                            # special-case is still an access requirement —
                            # reporting it as 'missing' would understate it.
                            extra = sorted(k for k in requirements if k.startswith("_"))
                            kind = f"requirement:{','.join(str(k) for k in extra)}"
                        elif isinstance(alias, str) and alias:
                            # Alias-only entries inherit another route's
                            # definition, often from a PHP route provider
                            # this YAML pass cannot read.
                            kind = f"alias:{alias}"
                        else:
                            kind = "missing"
                        controller_file = None
                        if isinstance(controller, str) and "::" in controller:
                            class_name = controller.split("::")[0].rsplit("\\", 1)[-1]
                            controller_file = classes.get(class_name)
                        routes.append(
                            {
                                "file": relative,
                                "name": name,
                                "route": definition.get("path"),
                                "controller": controller if isinstance(controller, str) else None,
                                "entity_form": entity_form if isinstance(entity_form, str) else None,
                                "controller_file": controller_file,
                                "access": kind,
                            }
                        )
        routes.sort(key=lambda row: (str(row["file"]), str(row["name"])))
        counts: dict[str, int] = {}
        for row in routes:
            kind = str(row["access"]).split(":", 1)[0]
            counts[kind] = counts.get(kind, 0) + 1
        payload: dict[str, Any] = {
            "target": {"module": module, "path": path},
            "routing_files": route_files,
            "routes": routes[:_MAX_ROUTES],
            "counts": counts,
            "truncated": len(routes) > _MAX_ROUTES,
        }
        anonymous = [row["name"] for row in routes if row["access"] == "anonymous"]
        missing = [row["name"] for row in routes if row["access"] == "missing"]
        if anonymous:
            payload["anonymous_routes"] = anonymous
            payload["note"] = (
                "Routes with access: TRUE are reachable without login; confirm "
                "each one is meant to be public."
            )
        if missing:
            payload["routes_missing_access"] = missing
            payload["note"] = (
                (payload.get("note", "") + " ")
                + f"{len(missing)} routes have no access requirement; Drupal then "
                "falls back to the controller's own checks — verify each."
            ).strip()
        aliases = [row for row in routes if str(row["access"]).startswith("alias:")]
        if aliases:
            payload["alias_routes"] = [row["name"] for row in aliases]
            payload["note"] = (
                (payload.get("note", "") + " ")
                + "Routes marked alias:NAME inherit another route's definition — "
                "often from a PHP route provider this YAML pass cannot read, so "
                "their access cannot be judged here."
            ).strip()
        if parse_errors:
            payload["parse_errors"] = parse_errors[:10]
        if not routes and not parse_errors:
            payload["note"] = "No *.routing.yml files in the target."
        return payload


