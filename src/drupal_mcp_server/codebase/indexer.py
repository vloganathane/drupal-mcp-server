"""Module indexer for scanning a local Drupal codebase.

Scanning approach adapted from drupal-scout-mcp (MIT, © David Loor),
extended here to multiple module locations (``modules``, ``web/modules``,
``sites/*/modules``, a configurable modules path, and core) with
exclusion of vendor/test scaffolding directories.
"""

import re
from pathlib import Path
from typing import Any

from .parsers import (
    parse_info_file,
    parse_php_file,
    parse_routing_file,
    parse_services_file,
)

#: Directories never worth descending into while indexing.
EXCLUDED_DIRS = {"node_modules", "vendor", "__pycache__", ".git", ".idea"}

#: Files larger than this are skipped by the PHP parsers.
MAX_PARSE_BYTES = 1_000_000


def _excluded_part(path: Path, base: Path) -> bool:
    """True when any part of ``path`` below ``base`` is an excluded dir."""
    try:
        parts = path.relative_to(base).parts
    except ValueError:
        parts = path.parts
    return any(part in EXCLUDED_DIRS or part.startswith(".") for part in parts)


def _tokenize(text: str) -> list[str]:
    return [word.lower() for word in re.findall(r"[a-zA-Z0-9]{3,}", text)]


class ModuleIndexer:
    """Scans a Drupal docroot and indexes its modules."""

    def __init__(self, root: Path, modules_path: str = "modules") -> None:
        self.root = root
        self.modules_path = modules_path
        self.modules: dict[str, list[dict[str, Any]]] = {
            "custom": [],
            "contrib": [],
            "core": [],
        }
        self.modules_dirs: list[Path] = []
        self.file_count: int = 0

    def index_all(self) -> dict[str, list[dict[str, Any]]]:
        """Scan every modules location and return the index by type."""
        self.modules = {"custom": [], "contrib": [], "core": []}
        self.modules_dirs = []
        self.file_count = 0

        seen: set[str] = set()
        for directory in self.module_locations():
            self.modules_dirs.append(directory)
            for info_file in self._scan_info_files(directory):
                module_dir = info_file.parent
                key = str(module_dir.resolve())
                if key in seen:
                    continue
                seen.add(key)
                record = self._index_module(module_dir)
                if record is not None:
                    self.modules[record["type"]].append(record)
        for group in self.modules.values():
            group.sort(key=lambda module: str(module["machine_name"]))
        return self.modules

    def module_locations(self) -> list[Path]:
        """Module directories that actually exist under the docroot.

        Covers the configured ``modules_path``, the classic ``modules``
        dir, composer's ``web/modules``, every ``sites/*/modules`` (both
        at the root and under ``web/``), and core's own modules.
        """
        locations: list[Path] = []
        seen: set[Path] = set()

        def add(path: Path) -> None:
            if not path.is_dir():
                return
            resolved = path.resolve()
            if resolved in seen:
                return
            seen.add(resolved)
            locations.append(path)

        add(self.root / self.modules_path)
        add(self.root / "modules")
        add(self.root / "web" / "modules")
        for sites in (self.root / "sites", self.root / "web" / "sites"):
            for site_dir in sorted(sites.glob("*")):
                add(site_dir / "modules")
        add(self.root / "core" / "modules")
        return locations

    def _scan_info_files(self, directory: Path) -> list[Path]:
        return sorted(
            path
            for path in directory.rglob("*.info.yml")
            if path.is_file() and not _excluded_part(path.parent, directory)
        )

    def _classify(self, module_dir: Path) -> str:
        """Classify a module by where it lives: custom, contrib, or core."""
        try:
            parts = module_dir.relative_to(self.root).parts
        except ValueError:
            parts = module_dir.parts
        if "core" in parts:
            return "core"
        if "custom" in parts:
            return "custom"
        return "contrib"

    def _index_module(self, module_dir: Path) -> dict[str, Any] | None:
        machine = module_dir.name
        module_type = self._classify(module_dir)

        info_path = module_dir / f"{machine}.info.yml"
        if not info_path.is_file():
            candidates = sorted(module_dir.glob("*.info.yml"))
            info_path = candidates[0] if candidates else info_path
        info: dict[str, Any] = parse_info_file(info_path) if info_path.is_file() else {}

        services_path = module_dir / f"{machine}.services.yml"
        services = parse_services_file(services_path) if services_path.is_file() else {}
        routing_path = module_dir / f"{machine}.routing.yml"
        routing = parse_routing_file(routing_path) if routing_path.is_file() else {}

        hooks: list[dict[str, Any]] = []
        for extension in (".module", ".install", ".theme", ".profile"):
            php_path = module_dir / f"{machine}{extension}"
            if not php_path.is_file() or php_path.stat().st_size > MAX_PARSE_BYTES:
                continue
            parsed = parse_php_file(php_path, module_name=machine)
            for hook in parsed.get("hooks", []):
                hooks.append({**hook, "file": php_path.name})

        classes: list[dict[str, Any]] = []
        if module_type != "core":
            # Parsing every core src/ file would take minutes on a real
            # site; core is indexed for discovery, not deep code search.
            classes = self._index_classes(module_dir)

        service_list = services.get("services", [])
        route_list = routing.get("routes", [])
        return {
            "machine_name": machine,
            "name": info.get("name") or machine,
            "description": info.get("description", ""),
            "type": module_type,
            "package": info.get("package", "Other"),
            "version": info.get("version", ""),
            "core_version_requirement": info.get("core_version_requirement", ""),
            "dependencies": info.get("dependencies", []),
            "keywords": _collect_keywords(info, service_list, route_list, hooks, classes),
            "services": service_list,
            "routes": route_list,
            "hooks": hooks,
            "classes": classes,
            "files": self._count_files(module_dir),
            "path": str(module_dir),
        }

    def _index_classes(self, module_dir: Path) -> list[dict[str, Any]]:
        classes: list[dict[str, Any]] = []
        src_dir = module_dir / "src"
        if not src_dir.is_dir():
            return classes
        for php_path in sorted(src_dir.rglob("*.php")):
            if not php_path.is_file() or _excluded_part(php_path, src_dir):
                continue
            if php_path.stat().st_size > MAX_PARSE_BYTES:
                continue
            parsed = parse_php_file(php_path)
            relative = php_path.relative_to(module_dir).as_posix()
            for cls in parsed.get("classes", []):
                classes.append({**cls, "file": relative})
        return classes

    def _count_files(self, module_dir: Path) -> int:
        count = 0
        for path in module_dir.rglob("*"):
            if path.is_file() and not _excluded_part(path, module_dir):
                count += 1
        self.file_count += count
        return count

    def get_module(self, machine_name: str) -> dict[str, Any] | None:
        """Look up one indexed module by machine name."""
        for group in self.modules.values():
            for module in group:
                if module["machine_name"] == machine_name:
                    return module
        return None


def _collect_keywords(
    info: dict[str, Any],
    services: list[dict[str, Any]],
    routes: list[dict[str, Any]],
    hooks: list[dict[str, Any]],
    classes: list[dict[str, Any]],
) -> list[str]:
    """Gather every searchable keyword across a module's parsed files."""
    keywords: list[str] = list(info.get("keywords", []))
    for service in services:
        keywords.extend(service.get("keywords", []))
    for route in routes:
        keywords.extend(route.get("keywords", []))
    for hook in hooks:
        keywords.extend(_tokenize(str(hook.get("name", ""))))
    for cls in classes:
        keywords.extend(_tokenize(str(cls.get("name", ""))))
    seen: set[str] = set()
    unique: list[str] = []
    for word in keywords:
        if word and word not in seen:
            seen.add(word)
            unique.append(word)
    return unique
