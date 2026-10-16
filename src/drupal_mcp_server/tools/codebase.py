"""Local codebase tools: index, search, and read a Drupal codebase on disk.

Every tool works against a local Drupal docroot (DRUPAL_ROOT) and never
touches the network. Each returns a dict; on failure the dict carries a
readable ``error`` key.
"""

import re
from typing import Any

from fastmcp import FastMCP

from ..codebase import UNAVAILABLE_MESSAGE, CodebaseService

_MACHINE_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _invalid_name(value: str, label: str) -> dict[str, Any]:
    return {
        "error": (
            f"Invalid {label} {value!r}: only letters, digits, and "
            "underscores are allowed (machine-name format)."
        )
    }


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    service: CodebaseService | None = deps.get("codebase_service")

    @mcp.tool()
    async def codebase_index_refresh() -> dict[str, Any]:
        """Rebuild the local codebase module index.

        Call after installing, enabling or creating modules so the other
        codebase tools see the current state. Returns counts of indexed
        modules by type and the module directories that were scanned.
        """
        if service is None or not service.available:
            return {"error": UNAVAILABLE_MESSAGE}
        try:
            return service.refresh()
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool()
    async def codebase_search(query: str, limit: int = 10, scope: str = "all") -> dict[str, Any]:
        """Search the local codebase for modules providing a capability.

        Ranks exact machine-name/name matches above description matches,
        which rank above code-body matches (hooks, services, routes,
        classes). Use scope 'custom' or 'contrib' to filter by module
        origin; 'all' includes core.
        """
        if service is None or not service.available:
            return {"error": UNAVAILABLE_MESSAGE}
        if scope not in ("all", "custom", "contrib"):
            return {"error": f"scope must be 'all', 'custom', or 'contrib'; got {scope!r}."}
        if not isinstance(limit, int) or limit < 1:
            return {"error": "limit must be a positive integer."}
        try:
            results = service.search(query, limit=limit, scope=scope)
        except Exception as exc:
            return {"error": str(exc)}
        return {"query": query, "scope": scope, "count": len(results), "results": results}

    @mcp.tool()
    async def codebase_module_list(
        scope: str = "all", show_unused: bool = False
    ) -> dict[str, Any]:
        """List indexed local modules with metadata.

        Each item carries machine name, human name, type (custom/contrib/
        core), version, dependencies, path and description. With
        show_unused=True each item is flagged when nothing references it
        and it implements no hooks.
        """
        if service is None or not service.available:
            return {"error": UNAVAILABLE_MESSAGE}
        if scope not in ("all", "custom", "contrib"):
            return {"error": f"scope must be 'all', 'custom', or 'contrib'; got {scope!r}."}
        try:
            modules = service.list_modules(scope=scope, show_unused=show_unused)
        except Exception as exc:
            return {"error": str(exc)}
        return {"count": len(modules), "modules": modules}

    @mcp.tool()
    async def codebase_module_describe(module: str) -> dict[str, Any]:
        """Describe one local module in full.

        Returns the module's info.yml fields, dependencies, reverse
        dependencies, hooks, services, routes, classes and file count —
        everything the index knows about it.
        """
        if service is None or not service.available:
            return {"error": UNAVAILABLE_MESSAGE}
        if not _MACHINE_NAME_RE.match(module):
            return _invalid_name(module, "module name")
        detail = service.describe(module)
        if detail is None:
            return {"error": f"Module {module!r} is not in the local index."}
        return detail

    @mcp.tool()
    async def codebase_unused_modules() -> dict[str, Any]:
        """List custom/contrib modules nothing references and that define no hooks.

        A module counts as used when another module depends on it, when
        another module's services inject one of its services, or when it
        implements hooks itself. Candidates for removal.
        """
        if service is None or not service.available:
            return {"error": UNAVAILABLE_MESSAGE}
        try:
            modules = service.unused_modules()
        except Exception as exc:
            return {"error": str(exc)}
        return {"count": len(modules), "modules": modules}

    @mcp.tool()
    async def codebase_redundancy_check(query: str) -> dict[str, Any]:
        """Check whether the local codebase already covers a capability.

        Searches the index and reports the closest existing modules plus
        a recommendation: extend what exists rather than duplicating it.
        """
        if service is None or not service.available:
            return {"error": UNAVAILABLE_MESSAGE}
        try:
            return service.redundancy_check(query)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool()
    async def codebase_hooks_find(hook_name: str) -> dict[str, Any]:
        """Find which local modules implement a hook, with file and line.

        Accepts the hook with or without its 'hook_' prefix (both
        'form_alter' and 'hook_form_alter' work). Implementations are
        reported per module with the file and line of the function.
        """
        if service is None or not service.available:
            return {"error": UNAVAILABLE_MESSAGE}
        if not _MACHINE_NAME_RE.match(hook_name):
            return _invalid_name(hook_name, "hook name")
        try:
            implementations = service.find_hooks(hook_name)
        except Exception as exc:
            return {"error": str(exc)}
        return {
            "hook": hook_name,
            "count": len(implementations),
            "implementations": implementations,
        }

    @mcp.tool()
    async def codebase_paths_list() -> dict[str, Any]:
        """Show the configured docroot and the module directories indexed.

        Use this to verify which locations the codebase tools actually
        scan (modules, web/modules, sites/*/modules, core) before relying
        on search results.
        """
        if service is None or not service.available:
            return {"error": UNAVAILABLE_MESSAGE}
        try:
            return service.paths()
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool()
    async def codebase_files_list(module: str) -> dict[str, Any]:
        """List every file in a local module as module-relative paths.

        Useful to find the right path before calling codebase_file_read
        or codebase_function_read.
        """
        if service is None or not service.available:
            return {"error": UNAVAILABLE_MESSAGE}
        if not _MACHINE_NAME_RE.match(module):
            return _invalid_name(module, "module name")
        files = service.list_files(module)
        if not files:
            return {"error": f"Module {module!r} is not in the local index (or has no files)."}
        return {"module": module, "count": len(files), "files": files}

    @mcp.tool()
    async def codebase_directory_tree(module: str) -> dict[str, Any]:
        """Show a local module's directory structure as a nested tree.

        Directories have children; files carry a size. The tree is depth
        and item capped to keep responses bounded.
        """
        if service is None or not service.available:
            return {"error": UNAVAILABLE_MESSAGE}
        if not _MACHINE_NAME_RE.match(module):
            return _invalid_name(module, "module name")
        return service.tree(module)

    @mcp.tool()
    async def codebase_file_read(module: str, path: str) -> dict[str, Any]:
        """Read one file from a local module.

        ``path`` is module-relative (e.g. 'mymod.module'). Content is
        truncated at 64 KB with a truncated flag. Absolute paths, '..'
        traversal and symlinks escaping the codebase are rejected.
        """
        if service is None or not service.available:
            return {"error": UNAVAILABLE_MESSAGE}
        if not _MACHINE_NAME_RE.match(module):
            return _invalid_name(module, "module name")
        return service.read_file(module, path)

    @mcp.tool()
    async def codebase_function_read(module: str, function_name: str) -> dict[str, Any]:
        """Extract a single PHP function (with its docblock) from a module.

        Returns the file path, the line of the function and its code —
        enough to review one hook or method without reading whole files.
        Searches all PHP-ish files in the module, including class methods.
        """
        if service is None or not service.available:
            return {"error": UNAVAILABLE_MESSAGE}
        if not _MACHINE_NAME_RE.match(module):
            return _invalid_name(module, "module name")
        if not _MACHINE_NAME_RE.match(function_name):
            return _invalid_name(function_name, "function name")
        found = service.read_function(module, function_name)
        if found is None:
            return {"error": f"Function {function_name!r} not found in module {module!r}."}
        return found
