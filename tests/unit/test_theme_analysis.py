"""Unit tests for the theme analysis tools added in Wave 4.

The contract under test: read-only inspection that never reaches a shell
with caller input, file access confined to DRUPAL_ROOT (a symlinked
info.yml or a `..` path in `pm:list` output must be rejected before the
read, not after), placements read from JSON:API rather than scout's
interpolated `drush ev`, and an existing-template check that reports
*why* it skipped instead of answering "absent" when it did not run.
"""

import asyncio
from pathlib import Path
from typing import Any

import drupal_mcp_server.tools.theme_analysis as theme_analysis


def _tool_functions(module: Any, **deps: Any) -> dict[str, Any]:
    class FakeMCP:
        def __init__(self) -> None:
            self.fns: dict[str, Any] = {}

        def tool(self, *args: Any, **kwargs: Any):
            def decorate(fn):
                self.fns[fn.__name__] = fn
                return fn

            return decorate

    mcp = FakeMCP()
    module.register_tools(mcp, **deps)
    return mcp.fns


class _Settings:
    def __init__(self, drupal_root: str | None) -> None:
        self.DRUPAL_ROOT = drupal_root


class _Drush:
    """run(*parts) answered by a handler receiving the same parts."""

    def __init__(self, handler: Any) -> None:
        self.handler = handler
        self.calls: list[tuple[Any, ...]] = []

    async def run(self, *parts: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(parts)
        return self.handler(*parts)


class _JSONAPI:
    """Paged JSON:API over a fixed resource map (no include resolution)."""

    def __init__(self, resources: dict[str, list[dict[str, Any]]]) -> None:
        self.resources = resources
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_resource(
        self, resource_type: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        params = dict(params or {})
        self.calls.append((resource_type, params))
        items = self.resources.get(resource_type, [])
        limit = int(params["page[limit]"]) if "page[limit]" in params else (len(items) or 50)
        offset = int(params["page[offset]"]) if "page[offset]" in params else 0
        return {"data": items[offset : offset + limit], "included": []}


_THEMES = {
    "testtheme": {
        "display_name": "Test Theme (testtheme)",
        "name": "testtheme",
        "type": "theme",
        "path": "core/themes/testtheme",
        "status": "Enabled",
        "version": "11.4.10",
        "package": "Core",
    },
    "stable9": {
        "display_name": "Stable 9 (stable9)",
        "name": "stable9",
        "type": "theme",
        "path": "core/themes/stable9",
        "status": "Disabled",
        "version": "11.4.10",
        "package": "Core",
    },
}

def _view_item(machine: str, label: str, displays: list[str]) -> dict[str, Any]:
    """One JSON:API view resource; the display dict mirrors the entity."""
    return {
        "type": "view--view",
        "id": f"uuid-view-{machine}",
        "attributes": {
            "drupal_internal__id": machine,
            "label": label,
            "status": True,
            "display": {
                display: {
                    "id": display,
                    "display_title": display.title(),
                    "display_plugin": "default" if display == "default" else "page",
                }
                for display in displays
            },
        },
    }


_VIEW_RESOURCES: dict[str, list[dict[str, Any]]] = {
    "view--view": [_view_item("frontpage", "Front page", ["default", "page_1"])]
}

_INFO_YML = """name: Test Theme
description: Fixture theme
type: theme
core_version_requirement: ^11
base theme: stable9
regions:
  header: Header
  content: Content
  footer: Footer
libraries:
  - testtheme/global
dependencies:
  - drupal:node
"""

_PARENT_INFO_YML = """name: Stable 9
type: theme
regions:
  content: Content
"""


def _drush_handler(
    themes: dict[str, Any] | None = None,
    default: str = "testtheme",
) -> Any:
    def handler(*parts: Any) -> dict[str, Any]:
        # Clients pass flags as a list part; flatten before dispatch.
        flat: list[Any] = []
        for part in parts:
            if isinstance(part, list):
                flat.extend(part)
            else:
                flat.append(part)
        command, args = str(flat[0]), [str(a) for a in flat[1:]]
        if command == "pm:list":
            return {"data": _THEMES if themes is None else themes}
        if command == "config:get" and args and args[0] == "system.theme":
            return {"data": {"default": default, "admin": "stable9"}}
        return {"data": {}, "stderr": f"unexpected drush call: {parts!r}"}

    return handler


def _block(
    bid: int,
    *,
    theme: str = "testtheme",
    region: str = "header",
    plugin: str = "system_branding_block",
    weight: int = 0,
    label: str = "Branding",
    status: bool = True,
    visibility: list[Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": "block--block",
        "id": f"uuid-{bid}",
        "attributes": {
            "drupal_internal__id": bid,
            "theme": theme,
            "region": region,
            "plugin": plugin,
            "weight": weight,
            "settings": {"label": label},
            "status": status,
            "visibility": visibility if visibility is not None else [],
        },
    }


def _make_root(root: Path) -> Path:
    """A docroot with one custom theme, its base theme, and Twig files."""
    theme = root / "core" / "themes" / "testtheme"
    (theme / "templates").mkdir(parents=True)
    (theme / "testtheme.info.yml").write_text(_INFO_YML, encoding="utf-8")
    (theme / "templates" / "node.html.twig").write_text("{{ content }}", encoding="utf-8")
    (theme / "templates" / "page.html.twig").write_text("<main></main>", encoding="utf-8")
    (theme / "templates" / "views-view--frontpage.html.twig").write_text(
        "{{ rows }}", encoding="utf-8"
    )
    parent = root / "core" / "themes" / "stable9"
    parent.mkdir(parents=True)
    (parent / "stable9.info.yml").write_text(_PARENT_INFO_YML, encoding="utf-8")
    core_templates = root / "core" / "modules" / "node" / "templates"
    core_templates.mkdir(parents=True)
    (core_templates / "node.html.twig").write_text("{{ content['#node'] }}", encoding="utf-8")
    views_templates = root / "core" / "modules" / "views" / "templates"
    views_templates.mkdir(parents=True)
    (views_templates / "views-view.html.twig").write_text("{{ rows }}", encoding="utf-8")
    return theme


def _deps(root: Path | None, *, jsonapi: Any = ..., drush: Any = ...) -> dict[str, Any]:
    deps: dict[str, Any] = {}
    if jsonapi is not ...:
        deps["jsonapi_client"] = jsonapi
    else:
        deps["jsonapi_client"] = _JSONAPI(
            {"block--block": [
                _block(1, region="header", plugin="system_branding_block", label="Site branding"),
                _block(2, region="content", plugin="system_menu_block:main",
                       weight=1, label="Main navigation"),
                _block(3, region="removed_region", plugin="system_help_block",
                       weight=0, label="Help", status=False),
                _block(4, theme="othetheme", plugin="system_breadcrumb_block",
                       label="Elsewhere"),
            ]}
        )
    if drush is ...:
        deps["drush_client"] = _Drush(_drush_handler())
    elif drush is None:
        deps["drush_client"] = None
    else:
        deps["drush_client"] = _Drush(drush)
    deps["_root"] = root
    return deps


def _set_root(monkeypatch: Any, root: Path | None) -> None:
    monkeypatch.setattr(
        theme_analysis, "get_settings", lambda: _Settings(str(root) if root else None)
    )


def _fns(monkeypatch: Any, tmp_path: Path, **kwargs: Any) -> dict[str, Any]:
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
    _make_root(root)
    _set_root(monkeypatch, root)
    deps = _deps(root, **kwargs)
    deps.pop("_root")
    return _tool_functions(theme_analysis, **deps)


# --- theme_active ----------------------------------------------------------


def test_theme_active_reports_default_admin_and_enabled(monkeypatch: Any, tmp_path: Path) -> None:
    fns = _fns(monkeypatch, tmp_path)
    result = asyncio.run(fns["theme_active"]())
    assert result["default"] == "testtheme"
    assert result["admin"] == "stable9"
    assert [row["name"] for row in result["enabled"]] == ["testtheme"]
    assert result["enabled_count"] == 1
    assert result["disabled_count"] == 1
    enabled = result["enabled"][0]
    assert enabled["path"] == "core/themes/testtheme"
    assert enabled["version"] == "11.4.10"


def test_theme_active_requires_drush(monkeypatch: Any, tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
    _make_root(root)
    _set_root(monkeypatch, root)
    fns = _tool_functions(theme_analysis, drush_client=None, jsonapi_client=None)
    assert "error" in asyncio.run(fns["theme_active"]())


# --- theme_info ------------------------------------------------------------


def test_theme_info_merges_pm_list_and_info_yml(monkeypatch: Any, tmp_path: Path) -> None:
    fns = _fns(monkeypatch, tmp_path)
    info = asyncio.run(fns["theme_info"]("testtheme"))
    assert info["label"] == "Test Theme"
    assert info["description"] == "Fixture theme"
    assert info["status"] == "Enabled"
    assert info["version"] == "11.4.10"
    assert info["core_version_requirement"] == "^11"
    # Declaration order from info.yml, not alphabetical.
    assert [region["id"] for region in info["regions"]] == ["header", "content", "footer"]
    assert info["libraries"] == ["testtheme/global"]
    assert info["dependencies"] == ["drupal:node"]
    assert [chain["name"] for chain in info["base_theme"]] == ["stable9"]
    assert info["base_theme"][0]["label"] == "Stable 9"
    assert info["base_theme"][0]["found"] is True


def test_theme_info_unknown_theme_lists_available(monkeypatch: Any, tmp_path: Path) -> None:
    fns = _fns(monkeypatch, tmp_path)
    result = asyncio.run(fns["theme_info"]("nope"))
    assert "not installed" in result["error"]
    assert result["available"] == ["stable9", "testtheme"]


def test_theme_info_rejects_invalid_name(monkeypatch: Any, tmp_path: Path) -> None:
    fns = _fns(monkeypatch, tmp_path)
    assert "error" in asyncio.run(fns["theme_info"]("../evil"))
    assert "error" in asyncio.run(fns["theme_info"]("two words"))


def test_theme_info_requires_drupal_root(monkeypatch: Any, tmp_path: Path) -> None:
    fns = _fns(monkeypatch, tmp_path)
    _set_root(monkeypatch, None)
    result = asyncio.run(fns["theme_info"]("testtheme"))
    assert "DRUPAL_ROOT" in result["error"]


def test_theme_info_rejects_escaping_theme_path(monkeypatch: Any, tmp_path: Path) -> None:
    """pm:list is trusted for discovery but not for confinement."""
    themes = dict(_THEMES)
    themes["testtheme"] = {**_THEMES["testtheme"], "path": "../../etc"}
    fns = _fns(monkeypatch, tmp_path, drush=_drush_handler(themes=themes))
    result = asyncio.run(fns["theme_info"]("testtheme"))
    assert "does not exist under DRUPAL_ROOT" in result["error"]


def test_theme_info_rejects_symlinked_info(monkeypatch: Any, tmp_path: Path) -> None:
    """A symlink at info.yml's name must not point the read outside."""
    fns = _fns(monkeypatch, tmp_path)
    root = tmp_path / "root"
    outside = tmp_path / "outside.yml"
    outside.write_text("name: Pwned\n", encoding="utf-8")
    info = root / "core" / "themes" / "testtheme" / "testtheme.info.yml"
    info.unlink()
    info.symlink_to(outside)
    result = asyncio.run(fns["theme_info"]("testtheme"))
    assert "error" in result
    assert "outside the docroot" in result["error"] or "No testtheme.info.yml" in result["error"]
    assert "Pwned" not in str(result)


# --- theme_regions ---------------------------------------------------------


def test_theme_regions_counts_and_flags_unknown_region(monkeypatch: Any, tmp_path: Path) -> None:
    fns = _fns(monkeypatch, tmp_path)
    result = asyncio.run(fns["theme_regions"]("testtheme"))
    by_id = {region["id"]: region for region in result["regions"]}
    assert list(by_id) == ["header", "content", "footer"]
    assert by_id["header"]["block_count"] == 1
    assert by_id["header"]["blocks"][0]["label"] == "Site branding"
    assert by_id["footer"]["block_count"] == 0  # empty regions stay visible
    assert result["total_blocks"] == 3  # the other theme's block is excluded
    # The placement in a region info.yml no longer defines is flagged.
    unknown = result["blocks_in_unknown_regions"]
    assert [row["label"] for row in unknown] == ["Help"]
    assert unknown[0]["status"] == "disabled"
    assert "will not render" in result["note"]


def test_theme_regions_requires_jsonapi(monkeypatch: Any, tmp_path: Path) -> None:
    fns = _fns(monkeypatch, tmp_path, jsonapi=None)
    assert "error" in asyncio.run(fns["theme_regions"]("testtheme"))


# --- theme_blocks ----------------------------------------------------------


def test_theme_blocks_filters_and_labels(monkeypatch: Any, tmp_path: Path) -> None:
    fns = _fns(monkeypatch, tmp_path)
    everything = asyncio.run(fns["theme_blocks"]())
    assert everything["total"] == 4
    assert everything["filters"] == {"theme_name": None, "region": None, "search": None}

    scoped = asyncio.run(fns["theme_blocks"](theme_name="testtheme", region="content"))
    assert [row["label"] for row in scoped["blocks"]] == ["Main navigation"]

    found = asyncio.run(fns["theme_blocks"](search="BRAND"))
    assert [row["label"] for row in found["blocks"]] == ["Site branding"]

    # Plugin text matches too, and status is a label, not a raw bool.
    plugin_hit = asyncio.run(fns["theme_blocks"](search="menu_block"))
    assert plugin_hit["total"] == 1
    help_row = asyncio.run(fns["theme_blocks"](search="help"))["blocks"][0]
    assert help_row["status"] == "disabled"
    assert help_row["visibility_rules"] == 0


def test_theme_blocks_rejects_bad_inputs(monkeypatch: Any, tmp_path: Path) -> None:
    fns = _fns(monkeypatch, tmp_path)
    assert "error" in asyncio.run(fns["theme_blocks"](region="not a region"))
    assert "error" in asyncio.run(fns["theme_blocks"](search=""))
    assert "error" in asyncio.run(fns["theme_blocks"](search="x" * 65))


# --- theme_templates -------------------------------------------------------


def test_theme_templates_lists_sizes_and_filters(monkeypatch: Any, tmp_path: Path) -> None:
    fns = _fns(monkeypatch, tmp_path)
    everything = asyncio.run(fns["theme_templates"]("testtheme"))
    assert everything["count"] == 3
    paths = [row["path"] for row in everything["templates"]]
    assert paths == [
        "templates/node.html.twig",
        "templates/page.html.twig",
        "templates/views-view--frontpage.html.twig",
    ]
    assert all(row["bytes"] > 0 for row in everything["templates"])
    assert everything["truncated"] is False

    filtered = asyncio.run(fns["theme_templates"]("testtheme", pattern="node"))
    assert filtered["count"] == 1
    assert filtered["pattern"] == "node"
    assert filtered["templates"][0]["path"] == "templates/node.html.twig"

    empty = asyncio.run(fns["theme_templates"]("testtheme", pattern="zzz"))
    assert empty["count"] == 0
    assert "No templates matching" in empty["note"]


def test_theme_templates_skips_symlinks(monkeypatch: Any, tmp_path: Path) -> None:
    """A link out of the docroot must not appear in the listing."""
    fns = _fns(monkeypatch, tmp_path)
    root = tmp_path / "root"
    outside = tmp_path / "outside.html.twig"
    outside.write_text("secret", encoding="utf-8")
    link = root / "core" / "themes" / "testtheme" / "templates" / "evil.html.twig"
    link.symlink_to(outside)
    result = asyncio.run(fns["theme_templates"]("testtheme"))
    paths = [row["path"] for row in result["templates"]]
    assert "templates/evil.html.twig" not in paths
    assert result["count"] == 3


def test_theme_templates_rejects_oversized_pattern(monkeypatch: Any, tmp_path: Path) -> None:
    fns = _fns(monkeypatch, tmp_path)
    assert "error" in asyncio.run(fns["theme_templates"]("testtheme", pattern=""))
    assert "error" in asyncio.run(fns["theme_templates"]("testtheme", pattern="x" * 65))


# --- theme_template_overrides ----------------------------------------------


def test_theme_template_overrides_splits_shadowed_and_original(
    monkeypatch: Any, tmp_path: Path
) -> None:
    fns = _fns(monkeypatch, tmp_path)
    result = asyncio.run(fns["theme_template_overrides"]("testtheme"))
    assert result["total_templates"] == 3
    overrides = {row["template"]: row for row in result["overrides"]}
    # The theme's node.html.twig shadows core's copy...
    assert "node.html.twig" in overrides
    assert overrides["node.html.twig"]["sources"] == [
        "core/modules/node/templates/node.html.twig"
    ]
    assert overrides["node.html.twig"]["theme_path"] == "templates/node.html.twig"
    # ...while page and views-view--frontpage exist only in the theme.
    assert sorted(row["template"] for row in result["theme_only"]) == [
        "page.html.twig",
        "views-view--frontpage.html.twig",
    ]
    # Only the two core templates live outside the theme itself.
    assert result["docroot_templates_scanned"] == 2


# --- template_suggestions --------------------------------------------------


def test_template_suggestions_marks_existing_default_theme(
    monkeypatch: Any, tmp_path: Path
) -> None:
    fns = _fns(monkeypatch, tmp_path)
    result = asyncio.run(fns["template_suggestions"]("node", "article"))
    assert result["entity_type"] == "node"
    assert result["bundle"] == "article"
    assert result["checked_in"] == "testtheme"
    by_name = {row["template"]: row for row in result["suggestions"]}
    # Bundle-specific suggestions come first and the base one is present.
    assert "node--article.html.twig" in by_name
    assert "node.html.twig" in by_name
    # The default theme ships node.html.twig but not node--article.html.twig.
    assert by_name["node.html.twig"]["in_checked_theme"] is True
    assert by_name["node--article.html.twig"]["in_checked_theme"] is False
    # Bracketed placeholders are described, not silently dropped.
    assert any("[nid]" in row["template"] for row in result["suggestions"])
    assert all(row["description"] for row in result["suggestions"])
    assert "note" not in result


def test_template_suggestions_unknown_entity_gets_generic_chain(
    monkeypatch: Any, tmp_path: Path
) -> None:
    fns = _fns(monkeypatch, tmp_path)
    result = asyncio.run(fns["template_suggestions"]("custom_thing", "widget"))
    names = [row["template"] for row in result["suggestions"]]
    assert names[0] == "custom_thing--widget.html.twig"
    assert names[-1] == "custom_thing.html.twig"


def test_template_suggestions_without_root_keeps_chain(
    monkeypatch: Any, tmp_path: Path
) -> None:
    fns = _fns(monkeypatch, tmp_path)
    _set_root(monkeypatch, None)
    result = asyncio.run(fns["template_suggestions"]("node", "article"))
    assert result["checked_in"] is None
    assert "DRUPAL_ROOT" in result["note"]
    # Unverified must read as None, never as False ("does not exist").
    assert all(row["in_checked_theme"] is None for row in result["suggestions"])


def test_template_suggestions_rejects_bad_identifiers(monkeypatch: Any, tmp_path: Path) -> None:
    fns = _fns(monkeypatch, tmp_path)
    assert "error" in asyncio.run(fns["template_suggestions"]("node; DROP"))
    assert "error" in asyncio.run(fns["template_suggestions"]("node", "bad bundle"))


# --- view_template_info ----------------------------------------------------


def test_view_template_info_builds_chain_from_real_displays(
    monkeypatch: Any, tmp_path: Path
) -> None:
    fns = _fns(monkeypatch, tmp_path, jsonapi=_JSONAPI(_VIEW_RESOURCES))
    result = asyncio.run(fns["view_template_info"]("frontpage"))
    assert result["label"] == "Front page"
    assert result["displays"] == ["default", "page_1"]
    assert result["checked_in"] == "testtheme"
    names = [row["template"] for row in result["suggestions"]]
    assert names == [
        "views-view--frontpage--default.html.twig",
        "views-view--frontpage--page_1.html.twig",
        "views-view--frontpage.html.twig",
        "views-view.html.twig",
    ]
    by_name = {row["template"]: row for row in result["suggestions"]}
    assert by_name["views-view--frontpage.html.twig"]["in_checked_theme"] is True
    assert by_name["views-view.html.twig"]["in_checked_theme"] is False


def test_view_template_info_specific_display_and_unknown_display(
    monkeypatch: Any, tmp_path: Path
) -> None:
    fns = _fns(monkeypatch, tmp_path, jsonapi=_JSONAPI(_VIEW_RESOURCES))
    scoped = asyncio.run(fns["view_template_info"]("frontpage", "page_1"))
    assert [row["template"] for row in scoped["suggestions"]] == [
        "views-view--frontpage--page_1.html.twig",
        "views-view--frontpage.html.twig",
        "views-view.html.twig",
    ]
    bad = asyncio.run(fns["view_template_info"]("frontpage", "nope"))
    assert "no display 'nope'" in bad["error"]
    assert bad["displays"] == ["default", "page_1"]


def test_view_template_info_unknown_view_and_bad_names(monkeypatch: Any, tmp_path: Path) -> None:
    fns = _fns(monkeypatch, tmp_path, jsonapi=_JSONAPI(_VIEW_RESOURCES))
    missing = asyncio.run(fns["view_template_info"]("missing_view"))
    assert "not found on this site" in missing["error"]
    assert missing["available"] == ["frontpage"]
    assert "error" in asyncio.run(fns["view_template_info"]("front-page"))
    assert "error" in asyncio.run(fns["view_template_info"]("frontpage", "1 bad"))


def test_view_template_info_requires_jsonapi(monkeypatch: Any, tmp_path: Path) -> None:
    fns = _fns(monkeypatch, tmp_path, jsonapi=None)
    result = asyncio.run(fns["view_template_info"]("frontpage"))
    assert "JSON:API" in result["error"]
