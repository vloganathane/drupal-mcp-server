"""Read-only theme analysis: metadata, regions, blocks, and Twig templates.

The counterpart of the theme_dev tools, which create things: these eight
tools only describe what exists. Theme metadata comes from
``drush pm:list`` plus a YAML parse of the theme's own ``info.yml``,
placements from the ``block--block`` JSON:API collection, and template
inspection walks the local docroot — always resolved first, so symlinked
or ``..`` paths that leave DRUPAL_ROOT are rejected before any read.
Nothing here interpolates caller input into shell commands.
"""

import os
from pathlib import Path
from typing import Any

import yaml
from fastmcp import FastMCP

from ..config import get_settings
from ..validation import validate_identifier
from ._utils import (
    drush_output,
    flag_label,
    jsonapi_attrs,
    jsonapi_collect,
)

# Walks stop here: these directories never hold Twig a site owns, and the
# public files directory would otherwise dominate the scan.
_SKIP_DIRS = {".git", "node_modules", "vendor", ".yarn", ".ddev", "libraries"}
_MAX_TEMPLATE_FILES = 5000
_MAX_SOURCES_PER_NAME = 10
_MAX_INFO_BYTES = 1_000_000
_MAX_BASE_THEME_DEPTH = 6
# Views to scan when looking one up by machine id (sites rarely exceed
# a few dozen; commerce distributions can reach into the low hundreds).
_MAX_VIEWS = 500
# Suggestion chains, most specific first. The bracketed parts are
# placeholders Drupal fills in at render time, not literal names.
_SUGGESTIONS: dict[str, list[tuple[str, str]]] = {
    "node": [
        ("node--[nid].html.twig", "Specific node by ID (e.g. node--123.html.twig)"),
        ("node--[view-mode].html.twig", "All nodes in a view mode (e.g. node--teaser.html.twig)"),
        ("node.html.twig", "All nodes (base template)"),
    ],
    "block": [
        ("block--[plugin-id].html.twig", "Specific block plugin (e.g. block--system-branding-block.html.twig)"),
        ("block--[region].html.twig", "All blocks in a region (e.g. block--sidebar.html.twig)"),
        ("block.html.twig", "All blocks (base template)"),
    ],
    "taxonomy_term": [
        ("taxonomy-term--[tid].html.twig", "Specific term by ID (e.g. taxonomy-term--5.html.twig)"),
        ("taxonomy-term.html.twig", "All taxonomy terms (base template)"),
    ],
    "user": [
        ("user--[uid].html.twig", "Specific user by ID (e.g. user--1.html.twig)"),
        ("user--[view-mode].html.twig", "Users in a view mode (e.g. user--compact.html.twig)"),
        ("user.html.twig", "All users (base template)"),
    ],
    "field": [
        ("field--[field-name]--[bundle].html.twig", "Specific field on a bundle (e.g. field--body--article.html.twig)"),
        ("field--[field-name].html.twig", "Specific field, all bundles (e.g. field--body.html.twig)"),
        ("field--[field-type].html.twig", "All fields of a type (e.g. field--text-with-summary.html.twig)"),
        ("field.html.twig", "All fields (base template)"),
    ],
    "page": [
        ("page--[path].html.twig", "Specific path (e.g. page--node--123.html.twig)"),
        ("page--[type].html.twig", "Page by type (e.g. page--article.html.twig)"),
        ("page.html.twig", "All pages (base template)"),
    ],
}
_BUNDLE_PREFIXED: dict[str, list[tuple[str, str]]] = {
    "node": [
        ("node--{bundle}--[nid].html.twig", "Specific {bundle} node by ID"),
        ("node--{bundle}--[view-mode].html.twig", "{bundle} node in a view mode"),
        ("node--{bundle}.html.twig", "All {bundle} nodes"),
    ],
    "block": [("block--{bundle}.html.twig", "All {bundle} blocks")],
    "taxonomy_term": [
        ("taxonomy-term--{bundle}--[tid].html.twig", "Specific {bundle} term by ID"),
        ("taxonomy-term--{bundle}.html.twig", "All {bundle} terms"),
    ],
    "field": [("field--{bundle}.html.twig", "All fields on {bundle}")],
}


def _drupal_root() -> str | None:
    """Configured Drupal root, or None when the server does not know one."""
    try:
        return get_settings().DRUPAL_ROOT
    except Exception:
        return None


def _inside_root(root: str, relative: str) -> Path | None:
    """Resolve ``relative`` under the docroot, or None if it escapes.

    Absolute segments, ``..`` traversal, and symlinks resolving outside
    the root all fail: the resolved path must sit inside DRUPAL_ROOT.
    """
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


async def _pm_themes(drush: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Theme inventory from ``drush pm:list``: keyed by machine name."""
    if not drush:
        return None, "Drush client not available"
    result = await drush.run("pm:list", ["--type=theme", "--format=json"])
    data = result.get("data") if isinstance(result, dict) else None
    if not isinstance(data, dict) or not data:
        return None, f"Could not list themes: {drush_output(result) if isinstance(result, dict) else 'no result'}"
    return {str(k): v for k, v in data.items() if isinstance(v, dict)}, None


async def _theme_context(
    drush: Any, root: str, themes: dict[str, Any], theme_name: str
) -> tuple[dict[str, Any] | None, Path | None, dict[str, Any] | None, dict[str, Any] | None]:
    """``(entry, directory, info.yml, error)`` for one theme."""
    entry = themes.get(theme_name)
    if entry is None:
        return None, None, None, {
            "error": f"Theme {theme_name!r} is not installed",
            "available": sorted(themes),
        }
    relative = str(entry.get("path") or "")
    directory = _inside_root(root, relative) if relative else None
    if directory is None or not directory.is_dir():
        return None, None, None, {
            "error": (
                f"Theme directory {relative!r} does not exist under DRUPAL_ROOT "
                f"({root}); file inspection needs a local docroot"
            )
        }
    # The info.yml itself must also resolve inside the docroot: a symlink
    # planted at the expected name could otherwise point the read outside
    # DRUPAL_ROOT. Exact name first, then a single unambiguous *.info.yml.
    root_resolved = Path(root).resolve()

    def confined(path: Path) -> Path | None:
        try:
            resolved = path.resolve()
        except OSError:
            return None
        if resolved.is_relative_to(root_resolved) and resolved.is_file():
            return resolved
        return None

    info_path = confined(directory / f"{theme_name}.info.yml")
    if info_path is None:
        fallback = sorted(directory.glob("*.info.yml"))
        info_path = confined(fallback[0]) if len(fallback) == 1 else None
    if info_path is None:
        return None, None, None, {
            "error": (
                f"No {theme_name}.info.yml found in {relative} inside DRUPAL_ROOT "
                f"(missing, or it resolves outside the docroot)"
            )
        }
    try:
        if info_path.stat().st_size > _MAX_INFO_BYTES:
            return None, None, None, {"error": f"{info_path.name} exceeds 1 MB; refusing to parse it"}
        parsed = yaml.safe_load(info_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, yaml.YAMLError) as exc:
        return None, None, None, {"error": f"Could not parse {info_path.name}: {exc}"}
    if not isinstance(parsed, dict):
        return None, None, None, {"error": f"{info_path.name} did not parse as a mapping"}
    return entry, directory, parsed, None


async def _default_theme(
    drush: Any, themes: dict[str, Any], root: str
) -> tuple[str | None, Path | None]:
    """Machine name and directory of the site's default theme."""
    if not drush:
        return None, None
    result = await drush.run("config:get", ["system.theme", "--format=json"])
    data = result.get("data") if isinstance(result, dict) else None
    name = data.get("default") if isinstance(data, dict) else None
    if not isinstance(name, str) or not name:
        return None, None
    entry = themes.get(name)
    relative = str((entry or {}).get("path") or "")
    directory = _inside_root(root, relative) if relative else None
    if directory is None or not directory.is_dir():
        return name, None
    return name, directory


def _walk_templates(base: Path, root: Path | None = None, exclude: Path | None = None) -> tuple[list[tuple[str, int]], bool]:
    """Pruned walk for ``*.html.twig`` under ``base``.

    Symlinks are skipped outright — a link pointing out of the docroot
    must not put an outside path into a response. Returns (path, bytes)
    pairs sorted by path and whether the file cap was hit.
    """
    results: list[tuple[str, int]] = []
    excluded = exclude.resolve() if exclude else None
    root_resolved = root.resolve() if root else base
    for dirpath, dirnames, filenames in os.walk(base):
        current = Path(dirpath)
        dirnames[:] = sorted(
            name
            for name in dirnames
            if name not in _SKIP_DIRS and not (name == "files" and current.name == "default")
        )
        for filename in sorted(filenames):
            if not filename.endswith(".html.twig"):
                continue
            path = current / filename
            if path.is_symlink():
                continue
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if not resolved.is_relative_to(root_resolved):
                continue
            if excluded and (resolved == excluded or resolved.is_relative_to(excluded)):
                continue
            try:
                size = path.lstat().st_size
            except OSError:
                continue
            rel = path.relative_to(base) if base in path.parents or path.parent == base else path.name
            results.append((str(rel), size))
            if len(results) >= _MAX_TEMPLATE_FILES:
                return sorted(results), True
    return sorted(results), False


def _index_other_templates(root: Path, exclude: Path) -> tuple[dict[str, list[str]], int]:
    """Map basename -> docroot-relative paths for every Twig file outside
    one theme; the source side of override detection."""
    index: dict[str, list[str]] = {}
    total = 0
    templates, _truncated = _walk_templates(root, root=root, exclude=exclude)
    for rel, _size in templates:
        total += 1
        name = Path(rel).name
        bucket = index.setdefault(name, [])
        if len(bucket) < _MAX_SOURCES_PER_NAME:
            # _walk_templates rooted at the docroot reports docroot-relative paths.
            bucket.append(rel)
    return index, total


def _suggestions_for(entity_type: str, bundle: str | None) -> list[tuple[str, str]]:
    """The Twig suggestion chain for one entity type, specific first."""
    suggestions: list[tuple[str, str]] = []
    if bundle:
        for template, description in _BUNDLE_PREFIXED.get(entity_type, []):
            suggestions.append((template.format(bundle=bundle), description.format(bundle=bundle)))
        if entity_type not in _BUNDLE_PREFIXED:
            suggestions.append((f"{entity_type}--{bundle}.html.twig", f"All {bundle} {entity_type}s"))
    suggestions.extend(_SUGGESTIONS.get(entity_type, []))
    if not suggestions:
        suggestions.append((f"{entity_type}.html.twig", f"All {entity_type}s (base template)"))
    elif entity_type not in _SUGGESTIONS and entity_type not in _BUNDLE_PREFIXED and bundle:
        suggestions.append((f"{entity_type}.html.twig", f"All {entity_type}s (base template)"))
    return suggestions


def _existing_stems(directory: Path | None, root: str | None) -> set[str] | None:
    """Template stems already present in a theme, or None if not checkable."""
    if directory is None or not root:
        return None
    templates, _truncated = _walk_templates(directory, root=Path(root))
    stems = {Path(rel).stem for rel, _size in templates}
    return stems


async def _checked_theme(
    drush: Any, root: str | None
) -> tuple[set[str] | None, str | None, str | None]:
    """``(stems, theme_name, skip_reason)`` for the default theme.

    The stems say which suggested template files already exist; the name
    says which theme was checked; and skip_reason explains why the check
    could not run, so an unverified suggestion is never presented as
    "absent".
    """
    if not root:
        return None, None, "DRUPAL_ROOT not configured; existing-template check skipped."
    if not drush:
        return None, None, "Drush not available; existing-template check skipped."
    themes, error = await _pm_themes(drush)
    if error or not themes:
        return None, None, "Could not list themes; existing-template check skipped."
    name, directory = await _default_theme(drush, themes, root)
    if name is None:
        return None, None, "Default theme unknown; existing-template check skipped."
    if directory is None:
        return None, name, f"Default theme directory for {name} not found under DRUPAL_ROOT."
    stems = _existing_stems(directory, root)
    if stems is None:
        return None, name, "Default theme has no readable templates; existing-template check skipped."
    return stems, name, None


def _mark(suggestions: list[tuple[str, str]], stems: set[str] | None) -> list[dict[str, Any]]:
    return [
        {
            "template": template,
            "description": description,
            "in_checked_theme": (Path(template).stem in stems) if stems is not None else None,
        }
        for template, description in suggestions
    ]


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    jsonapi = deps.get("jsonapi_client")
    drush = deps.get("drush_client")

    @mcp.tool()
    async def theme_active() -> dict[str, Any]:
        """List the site's themes: default, admin, and every enabled one.

        Reads system.theme and `drush pm:list`; returns the default and
        admin theme machine names plus each enabled theme's package,
        path, and version, with counts of the disabled ones.
        """
        if not drush:
            return {"error": "Drush client not available"}
        themes, error = await _pm_themes(drush)
        if error:
            return {"error": error}
        assert themes is not None
        result: dict[str, Any] = {"default": None, "admin": None}
        config = await drush.run("config:get", ["system.theme", "--format=json"])
        data = config.get("data") if isinstance(config, dict) else None
        if isinstance(data, dict):
            result["default"] = data.get("default")
            result["admin"] = data.get("admin")
        enabled = sorted(
            (
                {
                    "name": name,
                    "label": entry.get("display_name") or entry.get("name"),
                    "package": entry.get("package"),
                    "path": entry.get("path"),
                    "version": entry.get("version"),
                }
                for name, entry in themes.items()
                if str(entry.get("status", "")).lower() == "enabled"
            ),
            key=lambda row: str(row["name"]),
        )
        result["enabled"] = enabled
        result["enabled_count"] = len(enabled)
        result["disabled_count"] = len(themes) - len(enabled)
        return result

    @mcp.tool()
    async def theme_info(theme_name: str) -> dict[str, Any]:
        """Describe one theme: metadata, base-theme chain, regions, libraries.

        Combines `drush pm:list` (status, version, path) with a YAML parse
        of the theme's own .info.yml (description, regions in declaration
        order, libraries, dependencies) and follows the base theme chain
        upward as far as the site allows. Requires DRUPAL_ROOT: the
        info.yml lives on the local docroot.
        """
        invalid = validate_identifier(theme_name, "theme_name")
        if invalid is not None:
            return {"error": invalid}
        if not drush:
            return {"error": "Drush client not available"}
        themes, error = await _pm_themes(drush)
        if error:
            return {"error": error}
        assert themes is not None
        root = _drupal_root()
        if not root:
            return {"error": "DRUPAL_ROOT must point at a local Drupal docroot to read info.yml files"}
        entry, directory, info, err = await _theme_context(drush, root, themes, theme_name)
        if err:
            return err
        assert entry is not None and directory is not None and info is not None

        chain: list[dict[str, Any]] = []
        base = info.get("base theme") or info.get("basetheme")
        seen = {theme_name}
        while isinstance(base, str) and base and base not in seen and len(chain) < _MAX_BASE_THEME_DEPTH:
            seen.add(base)
            parent_entry = themes.get(base)
            if not isinstance(parent_entry, dict):
                chain.append({"name": base, "label": None, "path": None, "found": False})
                break
            parent_relative = str(parent_entry.get("path") or "")
            parent_dir = _inside_root(root, parent_relative) if parent_relative else None
            parent_info: dict[str, Any] = {}
            if parent_dir is not None and parent_dir.is_dir():
                candidate = parent_dir / f"{base}.info.yml"
                try:
                    resolved = candidate.resolve()
                    if resolved.is_relative_to(Path(root).resolve()) and resolved.is_file():
                        parsed = yaml.safe_load(resolved.read_text(encoding="utf-8", errors="replace"))
                        if isinstance(parsed, dict):
                            parent_info = parsed
                except (OSError, yaml.YAMLError):
                    parent_info = {}
            chain.append(
                {
                    "name": base,
                    "label": parent_info.get("name"),
                    "path": parent_relative or None,
                    "found": True,
                }
            )
            nxt = parent_info.get("base theme") or parent_info.get("basetheme")
            base = nxt if isinstance(nxt, str) else None

        regions = info.get("regions")
        libraries = info.get("libraries")
        dependencies = info.get("dependencies")
        return {
            "machine_name": theme_name,
            "label": info.get("name") or entry.get("display_name"),
            "description": info.get("description"),
            "version": entry.get("version"),
            "package": entry.get("package"),
            "status": entry.get("status"),
            "path": entry.get("path"),
            "core_version_requirement": info.get("core_version_requirement"),
            "hidden": bool(info.get("hidden")),
            "base_theme": chain,
            "regions": [
                {"id": str(region_id), "label": str(label)}
                for region_id, label in (regions or {}).items()
            ]
            if isinstance(regions, dict)
            else [],
            "libraries": [str(item) for item in libraries] if isinstance(libraries, list) else [],
            "dependencies": [str(item) for item in dependencies] if isinstance(dependencies, list) else [],
        }

    @mcp.tool()
    async def theme_regions(theme_name: str) -> dict[str, Any]:
        """Region layout of a theme with the blocks placed in each one.

        Regions come from the theme's info.yml in declaration order; each
        carries its blocks (label, plugin, weight, enabled state) and a
        count, so empty regions and placements in regions the theme no
        longer defines are both visible at a glance. Needs DRUPAL_ROOT
        (info.yml) and the JSON:API client (block placements).
        """
        if validate_identifier(theme_name, "theme_name") is not None:
            return {"error": f"Invalid theme_name: {theme_name!r}"}
        if not drush:
            return {"error": "Drush client not available"}
        if not jsonapi:
            return {"error": "JSON:API client not available"}
        themes, error = await _pm_themes(drush)
        if error:
            return {"error": error}
        assert themes is not None
        root = _drupal_root()
        if not root:
            return {"error": "DRUPAL_ROOT must point at a local Drupal docroot to read info.yml files"}
        entry, directory, info, err = await _theme_context(drush, root, themes, theme_name)
        if err:
            return err
        assert info is not None

        items, _included, _truncated = await jsonapi_collect(jsonapi, "block--block", {})
        blocks = [jsonapi_attrs(item) for item in items]
        theme_blocks = [block for block in blocks if block.get("theme") == theme_name]
        theme_blocks.sort(key=lambda block: (block.get("weight", 0), str(block.get("plugin", ""))))

        raw_regions = info.get("regions")
        region_info = raw_regions if isinstance(raw_regions, dict) else {}
        grouped: dict[str, list[dict[str, Any]]] = {str(rid): [] for rid in region_info}
        unknown: list[dict[str, Any]] = []
        for block in theme_blocks:
            row = {
                "id": block.get("drupal_internal__id"),
                "label": ((block.get("settings") or {}) if isinstance(block.get("settings"), dict) else {}).get("label")
                or block.get("plugin"),
                "plugin": block.get("plugin"),
                "weight": block.get("weight"),
                "status": flag_label(block.get("status"), "enabled", "disabled"),
            }
            region = str(block.get("region") or "")
            if region in grouped:
                grouped[region].append(row)
            else:
                unknown.append({**row, "region": region or "(none)"})

        payload: dict[str, Any] = {
            "theme": theme_name,
            "regions": [
                {
                    "id": str(region_id),
                    "label": str(label),
                    "block_count": len(grouped[str(region_id)]),
                    "blocks": grouped[str(region_id)],
                }
                for region_id, label in region_info.items()
            ],
            "total_blocks": len(theme_blocks),
        }
        if unknown:
            payload["blocks_in_unknown_regions"] = unknown
            payload["note"] = (
                "Some placements use regions this theme's info.yml does not define; "
                "they will not render."
            )
        if not region_info:
            payload["note"] = f"Theme {theme_name!r} defines no regions in its info.yml."
        return payload

    @mcp.tool()
    async def theme_blocks(
        theme_name: str | None = None,
        region: str | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        """List placed blocks with optional theme, region, and text filters.

        Reads every block.block.* placement from JSON:API: id, theme,
        region, label, plugin, weight, and enabled state. search matches
        label and plugin case-insensitively (the "do we have a block like
        Site branding?" question); theme_name and region narrow the list
        to one placement set. With no filters every placement on the site
        is returned, most specific sort first (theme, region, weight).
        """
        for value, label in ((theme_name, "theme_name"), (region, "region")):
            if value is not None and validate_identifier(value, label) is not None:
                return {"error": f"Invalid {label}: {value!r}"}
        if search is not None:
            search = search.strip()
            if not search or len(search) > 64:
                return {"error": "search must be 1-64 characters"}
        if not jsonapi:
            return {"error": "JSON:API client not available"}

        items, _included, _truncated = await jsonapi_collect(jsonapi, "block--block", {})
        rows: list[dict[str, Any]] = []
        needle = search.casefold() if search else None
        for item in items:
            block = jsonapi_attrs(item)
            if theme_name and block.get("theme") != theme_name:
                continue
            if region and str(block.get("region") or "") != region:
                continue
            raw_settings = block.get("settings")
            settings = raw_settings if isinstance(raw_settings, dict) else {}
            label_value = str(settings.get("label") or block.get("plugin") or "")
            plugin = str(block.get("plugin") or "")
            if needle and needle not in label_value.casefold() and needle not in plugin.casefold():
                continue
            visibility = block.get("visibility")
            rows.append(
                {
                    "id": block.get("drupal_internal__id"),
                    "theme": block.get("theme"),
                    "region": block.get("region"),
                    "label": label_value,
                    "plugin": plugin,
                    "weight": block.get("weight"),
                    "status": flag_label(block.get("status"), "enabled", "disabled"),
                    "visibility_rules": len(visibility) if isinstance(visibility, list) else 0,
                }
            )
        rows.sort(
            key=lambda row: (
                str(row["theme"] or ""),
                str(row["region"] or ""),
                row["weight"] if isinstance(row["weight"], (int, float)) else 0,
                str(row["label"]),
            )
        )
        return {
            "blocks": rows,
            "total": len(rows),
            "filters": {"theme_name": theme_name, "region": region, "search": search},
        }

    @mcp.tool()
    async def theme_templates(theme_name: str, pattern: str | None = None) -> dict[str, Any]:
        """List a theme's Twig templates (``*.html.twig``) with sizes.

        Walks the theme directory on the local docroot (symlinks skipped,
        nothing outside DRUPAL_ROOT reported). pattern is a
        case-insensitive substring matched against the template name —
        "node--", "views", "field" — to narrow the list. Returns
        docroot-relative paths and byte sizes, sorted.
        """
        if validate_identifier(theme_name, "theme_name") is not None:
            return {"error": f"Invalid theme_name: {theme_name!r}"}
        if pattern is not None:
            pattern = pattern.strip()
            if not pattern or len(pattern) > 64:
                return {"error": "pattern must be 1-64 characters"}
        if not drush:
            return {"error": "Drush client not available"}
        themes, error = await _pm_themes(drush)
        if error:
            return {"error": error}
        assert themes is not None
        root = _drupal_root()
        if not root:
            return {"error": "DRUPAL_ROOT must point at a local Drupal docroot to inspect templates"}
        _entry, directory, _info, err = await _theme_context(drush, root, themes, theme_name)
        if err:
            return err
        assert directory is not None

        found, truncated = _walk_templates(directory, root=Path(root))
        if pattern:
            needle = pattern.casefold()
            found = [(rel, size) for rel, size in found if needle in Path(rel).stem.casefold()]
        payload: dict[str, Any] = {
            "theme": theme_name,
            "count": len(found),
            "templates": [{"path": rel, "bytes": size} for rel, size in found],
            "truncated": truncated,
        }
        if pattern:
            payload["pattern"] = pattern
        if not found:
            payload["note"] = (
                f"No templates matching {pattern!r} in {theme_name}"
                if pattern
                else f"Theme {theme_name} ships no Twig templates"
            )
        return payload

    @mcp.tool()
    async def theme_template_overrides(theme_name: str) -> dict[str, Any]:
        """Which core/module templates a theme overrides, and which it invented.

        For every Twig file in the theme, the docroot is indexed once for
        files with the same name outside that theme; a match means the
        theme's copy wins at render time (an override), no match means a
        theme-original template. Returns both lists with paths, plus how
        many Twig files were scanned. Requires DRUPAL_ROOT.
        """
        if validate_identifier(theme_name, "theme_name") is not None:
            return {"error": f"Invalid theme_name: {theme_name!r}"}
        if not drush:
            return {"error": "Drush client not available"}
        themes, error = await _pm_themes(drush)
        if error:
            return {"error": error}
        assert themes is not None
        root = _drupal_root()
        if not root:
            return {"error": "DRUPAL_ROOT must point at a local Drupal docroot to inspect templates"}
        _entry, directory, _info, err = await _theme_context(drush, root, themes, theme_name)
        if err:
            return err
        assert directory is not None

        own, truncated = _walk_templates(directory, root=Path(root))
        index, scanned = _index_other_templates(Path(root), exclude=directory)
        overrides: list[dict[str, Any]] = []
        theme_only: list[dict[str, Any]] = []
        for rel, _size in own:
            name = Path(rel).name
            sources = index.get(name)
            if sources:
                overrides.append({"template": name, "theme_path": rel, "sources": sources})
            else:
                theme_only.append({"template": name, "theme_path": rel})
        return {
            "theme": theme_name,
            "total_templates": len(own),
            "overrides": overrides,
            "theme_only": theme_only,
            "docroot_templates_scanned": scanned,
            "truncated": truncated,
        }

    @mcp.tool()
    async def template_suggestions(entity_type: str, bundle: str | None = None) -> dict[str, Any]:
        """Twig template names Drupal will try for an entity, specific first.

        The suggestion chain for node, block, taxonomy_term, user, field,
        or page rendering (bracketed parts are placeholders Drupal fills
        in, e.g. node--article--123.html.twig beats node--article.html.twig).
        Unknown entity types get the generic chain. When DRUPAL_ROOT is
        configured each suggestion is marked in_checked_theme: whether the
        default theme already ships that file, so you know which name
        creating one would actually take effect.
        """
        if validate_identifier(entity_type, "entity_type") is not None:
            return {"error": f"Invalid entity_type: {entity_type!r}"}
        if bundle is not None and validate_identifier(bundle, "bundle") is not None:
            return {"error": f"Invalid bundle: {bundle!r}"}

        suggestions = _suggestions_for(entity_type, bundle)
        checked, checked_in, note = await _checked_theme(drush, _drupal_root())
        payload: dict[str, Any] = {
            "entity_type": entity_type,
            "bundle": bundle,
            "suggestions": _mark(suggestions, checked),
            "checked_in": checked_in,
        }
        if note:
            payload["note"] = note
        return payload

    @mcp.tool()
    async def view_template_info(view_name: str, display_id: str | None = None) -> dict[str, Any]:
        """Template names for overriding a Views display, verified against the site.

        Looks the view up in the JSON:API view collection by its machine
        id (drupal_internal__id), so the display list is real: with
        display_id the chain starts at views-view--NAME--DISPLAY and
        falls back to the whole view; without it every display gets an
        entry, then the views-view base template. An unknown view errors
        with the views the site has, an unknown display_id with the
        displays that view has, and suggestions are marked
        in_checked_theme when the default theme's templates can be read
        (DRUPAL_ROOT). Views config changed names between Drupal
        generations (view.* on older sites, views.view.* on Drupal 11.4+),
        so the collection — addressed by entity id — is the stable source.
        """
        if validate_identifier(view_name, "view_name") is not None:
            return {"error": f"Invalid view_name: {view_name!r}"}
        if display_id is not None and validate_identifier(display_id, "display_id") is not None:
            return {"error": f"Invalid display_id: {display_id!r}"}
        if not jsonapi:
            return {"error": "JSON:API client not available"}

        items, _included, _truncated = await jsonapi_collect(
            jsonapi, "view--view", {}, max_items=_MAX_VIEWS
        )
        known: dict[str, dict[str, Any]] = {}
        for item in items:
            attrs = jsonapi_attrs(item)
            machine_id = attrs.get("drupal_internal__id")
            if isinstance(machine_id, str) and machine_id:
                known[machine_id] = attrs
        data = known.get(view_name)
        if data is None:
            return {
                "error": f"View {view_name!r} not found on this site",
                "available": sorted(known)[:50],
            }
        raw_display = data.get("display")
        displays = sorted(raw_display) if isinstance(raw_display, dict) else []

        if display_id is not None:
            if displays and display_id not in displays:
                return {
                    "error": f"View {view_name!r} has no display {display_id!r}",
                    "displays": displays,
                }
            chain = [
                (f"views-view--{view_name}--{display_id}.html.twig", "This display only (most specific)"),
                (f"views-view--{view_name}.html.twig", "All displays of this view"),
            ]
        else:
            chain = [
                (f"views-view--{view_name}--{display}.html.twig", f"Display {display}")
                for display in displays
            ]
            chain.append((f"views-view--{view_name}.html.twig", "All displays of this view"))
        chain.append(("views-view.html.twig", "All views (base template)"))

        checked, checked_in, note = await _checked_theme(drush, _drupal_root())
        payload: dict[str, Any] = {
            "view": view_name,
            "label": data.get("label"),
            "displays": displays,
            "display_id": display_id,
            "suggestions": _mark(chain, checked),
            "checked_in": checked_in,
        }
        if note:
            payload["note"] = note
        return payload
