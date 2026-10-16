"""Local Drupal codebase index and search.

Core indexing and search approach adapted from drupal-scout-mcp
(MIT, © David Loor), hardened for MCP exposure: every file read is
resolved against the configured docroot and rejected when it escapes
the module directory (absolute paths, ``..`` traversal, and symlinks
that resolve outside the root are all refused).
"""

from pathlib import Path
from typing import Any

from .indexer import EXCLUDED_DIRS, ModuleIndexer
from .parsers import extract_php_function
from .search import ModuleSearcher, scope_types

#: Shown by the tools when no usable local codebase is configured.
UNAVAILABLE_MESSAGE = (
    "DRUPAL_ROOT is not set to an existing Drupal codebase; "
    "set it to enable local codebase tools."
)

#: ``read_file`` truncates content at 64 KB and flags the truncation.
MAX_READ_BYTES = 64 * 1024

#: Files larger than this are skipped by ``read_function``.
MAX_FUNCTION_FILE_BYTES = 1_000_000

#: Extensions that may contain PHP functions worth extracting.
PHP_EXTENSIONS = (".php", ".module", ".install", ".theme", ".inc", ".profile")

_TREE_MAX_DEPTH = 5
_TREE_MAX_ITEMS = 400


class CodebaseService:
    """Indexes a local Drupal docroot and answers queries about it.

    ``root`` is the Drupal docroot (or ``None`` for "not configured").
    ``modules_path`` is the modules directory relative to the root
    (``"web/modules"`` for composer installs); in addition to it, the
    classic ``modules``, ``web/modules`` and ``sites/*/modules``
    locations are always scanned when they exist. The index is built
    lazily on first use and cached until :meth:`refresh` is called.
    """

    def __init__(self, root: str | None, modules_path: str = "modules") -> None:
        self.root = Path(root).expanduser() if root else None
        self.modules_path = modules_path
        self._indexer: ModuleIndexer | None = None
        self._searcher: ModuleSearcher | None = None

    @property
    def available(self) -> bool:
        """True when a root is configured and points at a directory."""
        return self.root is not None and self.root.is_dir()

    # -- index lifecycle -------------------------------------------------

    def _ensure_index(self) -> ModuleIndexer:
        if self._indexer is None:
            if self.root is None:
                raise RuntimeError(UNAVAILABLE_MESSAGE)
            self._indexer = ModuleIndexer(self.root, modules_path=self.modules_path)
            self._indexer.index_all()
            self._searcher = ModuleSearcher(self._indexer)
        return self._indexer

    def _ensure_searcher(self) -> ModuleSearcher:
        self._ensure_index()
        if self._searcher is None:  # pragma: no cover - set with the index
            raise RuntimeError("Index not initialized.")
        return self._searcher

    def refresh(self) -> dict[str, Any]:
        """Rebuild the index from disk and summarize what was found."""
        if self.root is None:
            raise RuntimeError(UNAVAILABLE_MESSAGE)
        indexer = ModuleIndexer(self.root, modules_path=self.modules_path)
        indexer.index_all()
        self._indexer = indexer
        self._searcher = ModuleSearcher(indexer)
        return {
            "modules": sum(len(group) for group in indexer.modules.values()),
            "custom": len(indexer.modules["custom"]),
            "contrib": len(indexer.modules["contrib"]),
            "core": len(indexer.modules["core"]),
            "files": indexer.file_count,
            "modules_dirs": [str(directory) for directory in indexer.modules_dirs],
        }

    # -- queries ---------------------------------------------------------

    def search(self, query: str, limit: int = 10, scope: str = "all") -> list[dict[str, Any]]:
        """Rank modules matching a functionality query.

        Raises ``ValueError`` for an unknown scope. Ranking: exact
        machine-name/name matches first, then description, then code.
        """
        return self._ensure_searcher().search(query, limit=limit, scope=scope)

    def search_modules(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Recommendation-oriented search: name, type and match reason."""
        return self._ensure_searcher().search_modules(query, limit=limit)

    def list_modules(self, scope: str = "all", show_unused: bool = False) -> list[dict[str, Any]]:
        """List indexed modules with metadata.

        With ``show_unused=True`` each item carries an ``unused`` flag for
        modules with no hook implementations that nothing references.
        """
        unused_names: set[str] = set()
        if show_unused:
            unused_names = {
                str(item["machine_name"]) for item in self._ensure_searcher().unused_modules()
            }
        modules: list[dict[str, Any]] = []
        for module_type in scope_types(scope):
            for record in self._ensure_index().modules.get(module_type, []):
                item: dict[str, Any] = {
                    "machine_name": record["machine_name"],
                    "name": record["name"],
                    "type": record["type"],
                    "version": record.get("version", ""),
                    "dependencies": record.get("dependencies", []),
                    "path": record.get("path", ""),
                    "description": record.get("description", ""),
                }
                if show_unused:
                    item["unused"] = record["machine_name"] in unused_names
                modules.append(item)
        return modules

    def describe(self, module: str) -> dict[str, Any] | None:
        """Full record for one module, including reverse dependencies."""
        record = self._ensure_index().get_module(module)
        if record is None:
            return None
        detail = dict(record)
        detail["reverse_dependencies"] = [
            {
                "machine_name": other["machine_name"],
                "name": other["name"],
                "type": other["type"],
            }
            for other in self._ensure_searcher().all_modules()
            if module in [str(dep) for dep in other.get("dependencies", [])]
        ]
        return detail

    def unused_modules(self) -> list[dict[str, Any]]:
        """Custom/contrib modules nothing references and that define no hooks."""
        return self._ensure_searcher().unused_modules()

    def redundancy_check(self, query: str) -> dict[str, Any]:
        """Existing functionality in this codebase that covers a query."""
        return self._ensure_searcher().redundancy_check(query)

    def find_hooks(self, hook_name: str) -> list[dict[str, Any]]:
        """Which modules implement a hook, with file and line."""
        return self._ensure_searcher().find_hooks(hook_name)

    def paths(self) -> dict[str, Any]:
        """The configured root and the absolute module dirs that were indexed."""
        indexer = self._ensure_index()
        return {
            "root": str(self.root) if self.root is not None else None,
            "modules": [str(directory) for directory in indexer.modules_dirs],
        }

    # -- file access (path-safe) ------------------------------------------

    def list_files(self, module: str) -> list[str]:
        """Module-relative paths of every file in the module."""
        base = self._module_dir(module)
        if base is None:
            return []
        return _walk_files(base)

    def tree(self, module: str) -> dict[str, Any]:
        """Nested directory tree of a module, depth- and item-capped."""
        base = self._module_dir(module)
        if base is None:
            return {"error": f"Module {module!r} is not in the index."}
        return _build_tree(base, max_depth=_TREE_MAX_DEPTH, max_items=_TREE_MAX_ITEMS)

    def read_file(self, module: str, relpath: str) -> dict[str, Any]:
        """Read a module-relative file; content truncated at 64 KB.

        Absolute paths, ``..`` traversal, and symlinks resolving outside
        the module directory are rejected with an ``error`` dict.
        """
        base = self._module_dir(module)
        if base is None:
            return {"error": f"Module {module!r} is not in the index."}
        target = _resolve_inside(base, relpath)
        if target is None:
            return {
                "error": (
                    f"Path {relpath!r} resolves outside module {module!r}; "
                    "absolute paths, '..' traversal, and symlinks escaping "
                    "the codebase are rejected."
                )
            }
        if not target.is_file():
            return {"error": f"{relpath!r} is not a regular file."}
        try:
            data = target.read_bytes()
        except OSError as exc:
            return {"error": f"Could not read {relpath!r}: {exc}"}
        truncated = len(data) > MAX_READ_BYTES
        content = data[:MAX_READ_BYTES].decode("utf-8", errors="replace")
        return {
            "path": relpath,
            "size": len(data),
            "content": content,
            "truncated": truncated,
        }

    def read_function(self, module: str, function_name: str) -> dict[str, Any] | None:
        """Extract one PHP function (with docblock) from the module."""
        base = self._module_dir(module)
        if base is None:
            return None
        for relpath in _walk_files(base):
            if not relpath.endswith(PHP_EXTENSIONS):
                continue
            file_path = base / relpath
            try:
                if file_path.stat().st_size > MAX_FUNCTION_FILE_BYTES:
                    continue
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            found = extract_php_function(content, function_name)
            if found is not None:
                line, code = found
                return {"path": relpath, "line": line, "code": code}
        return None

    def _module_dir(self, module: str) -> Path | None:
        record = self._ensure_index().get_module(module)
        if record is None:
            return None
        return Path(str(record["path"]))


def _resolve_inside(base: Path, relpath: str) -> Path | None:
    """Resolve ``relpath`` strictly inside ``base`` or return ``None``.

    ``Path.resolve()`` follows symlinks, so a link pointing at a file
    outside the module resolves to a path that is no longer relative to
    ``base`` and is refused by the same containment check as ``..``.
    """
    if Path(relpath).is_absolute():
        return None
    try:
        resolved_base = base.resolve()
        candidate = (base / relpath).resolve()
    except OSError:
        return None
    if not candidate.is_relative_to(resolved_base):
        return None
    return candidate


def _walk_files(base: Path) -> list[str]:
    """Sorted module-relative paths of all files below ``base``."""
    files: list[str] = []
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(base)
        if any(part in EXCLUDED_DIRS or part.startswith(".") for part in relative.parts[:-1]):
            continue
        files.append(relative.as_posix())
    return sorted(files)


def _build_tree(path: Path, max_depth: int, max_items: int) -> dict[str, Any]:
    """Nested tree of dirs/files, capped to keep responses bounded."""
    budget = [max_items]
    truncated = [False]

    def build(current: Path, depth: int) -> dict[str, Any]:
        node: dict[str, Any] = {"name": current.name, "type": "dir", "children": []}
        try:
            entries = sorted(current.iterdir(), key=lambda entry: (entry.is_dir(), entry.name))
        except OSError:
            return node
        for entry in entries:
            if entry.name in EXCLUDED_DIRS or entry.name.startswith("."):
                continue
            if budget[0] <= 0:
                truncated[0] = True
                break
            budget[0] -= 1
            if entry.is_dir():
                if depth + 1 < max_depth:
                    node["children"].append(build(entry, depth + 1))
                else:
                    node["children"].append(
                        {"name": entry.name, "type": "dir", "children": [], "truncated": True}
                    )
                    truncated[0] = True
            else:
                child: dict[str, Any] = {"name": entry.name, "type": "file"}
                try:
                    child["size"] = entry.stat().st_size
                except OSError:
                    child["size"] = None
                node["children"].append(child)
        if truncated[0]:
            node["truncated"] = True
        return node

    tree = build(path, 0)
    tree["truncated"] = truncated[0]
    return tree
