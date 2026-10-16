"""Unit tests for the local codebase index/search service and tools.

Builds a throwaway fake Drupal docroot in tmp_path (custom, contrib,
core, sites/*/modules and web/modules locations, plus a secret file
outside the root with a symlink pointing at it) and exercises the
service and the MCP tools against it. No network, no subprocesses.
"""

import os
from pathlib import Path
from typing import Any

import pytest

from drupal_mcp_server.codebase import CodebaseService
from drupal_mcp_server.tools import codebase as codebase_tools

MYMOD_MODULE = """<?php

/**
 * Implements hook_form_alter().
 */
function mymod_form_alter(&$form, $form_state) {
  $form['mymod'] = ['#type' => 'markup', '#markup' => 'hi'];
}

/**
 * Implements hook_help().
 */
function mymod_help($route_name, $route_match) {
  return 'Help text';
}
"""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture()
def docroot(tmp_path: Path) -> Path:
    root = tmp_path / "docroot"
    # A file OUTSIDE the docroot, with a symlink to it INSIDE a module.
    (tmp_path / "secret.txt").write_text("TOP SECRET", encoding="utf-8")

    _write(root / "core" / "lib" / "Drupal.php", "<?php class Drupal { const VERSION = '11.0.0'; }")

    mymod = root / "modules" / "custom" / "mymod"
    _write(
        mymod / "mymod.info.yml",
        "name: 'My Module'\n"
        "type: module\n"
        "description: 'Site settings and other module integration helpers.'\n"
        "package: Custom\n"
        "version: '1.2.0'\n"
        "core_version_requirement: ^10 || ^11\n"
        "keywords: [settings, integration]\n"
        "dependencies:\n"
        "  - drupal:node\n"
        "  - webmod\n",
    )
    _write(mymod / "mymod.module", MYMOD_MODULE)
    _write(
        mymod / "mymod.services.yml",
        "services:\n"
        "  mymod.settings:\n"
        "    class: Drupal\\mymod\\Settings\n"
        "    arguments: ['@config.factory']\n",
    )
    _write(
        mymod / "mymod.routing.yml",
        "mymod.settings_form:\n"
        "  path: '/admin/config/system/mymod'\n"
        "  defaults:\n"
        "    _form: 'Drupal\\mymod\\Form\\SettingsForm'\n"
        "  requirements:\n"
        "    _permission: 'administer mymod'\n",
    )
    _write(
        mymod / "src" / "Plugin" / "Foo.php",
        "<?php\n"
        "\n"
        "namespace Drupal\\mymod\\Plugin;\n"
        "\n"
        "class Foo extends Bar {\n"
        "\n"
        "  /**\n"
        "   * Builds the thing.\n"
        "   */\n"
        "  public function build() {\n"
        "    return [];\n"
        "  }\n"
        "\n"
        "}\n",
    )
    _write(mymod / "big.txt", "x" * 70_000)
    os.symlink(str(tmp_path / "secret.txt"), str(mymod / "secret_link.txt"))

    _write(
        root / "modules" / "contrib" / "othermod" / "othermod.info.yml",
        "name: 'Other Module'\n"
        "type: module\n"
        "description: 'Provides PDF generation for content entities.'\n"
        "package: Content\n"
        "version: '2.0.1'\n"
        "dependencies:\n"
        "  - drupal:node\n",
    )

    sitemod = root / "sites" / "default" / "modules" / "custom" / "sitemod"
    _write(
        sitemod / "sitemod.info.yml",
        "name: 'Site Module'\n"
        "description: 'Site-specific alterations.'\n"
        "dependencies:\n"
        "  - drupal:node\n"
        "  - mymod\n",
    )
    _write(
        sitemod / "sitemod.module",
        "<?php\n\n"
        "/**\n * Implements hook_form_alter().\n */\n"
        "function sitemod_form_alter(&$form, $form_state) {\n"
        "  $form['sitemod'] = [];\n"
        "}\n",
    )

    _write(
        root / "web" / "modules" / "contrib" / "webmod" / "webmod.info.yml",
        "name: 'Web Module'\n"
        "description: 'Composer-managed helper.'\n"
        "dependencies: []\n",
    )

    # Only indexed when modules_path points at it explicitly.
    _write(
        root / "apps" / "modules" / "custom" / "appmod" / "appmod.info.yml",
        "name: 'App Module'\n"
        "description: 'Lives in a non-standard modules dir.'\n"
        "dependencies: []\n",
    )
    return root


@pytest.fixture()
def service(docroot: Path) -> CodebaseService:
    return CodebaseService(str(docroot))


# --- index build -----------------------------------------------------------


def test_available_requires_an_existing_root(tmp_path: Path, docroot: Path):
    assert CodebaseService(str(docroot)).available is True
    assert CodebaseService(None).available is False
    assert CodebaseService(str(tmp_path / "nope")).available is False


def test_refresh_summarizes_the_index(service: CodebaseService):
    summary = service.refresh()

    assert summary["modules"] == 4
    assert summary["custom"] == 2  # mymod, sitemod
    assert summary["contrib"] == 2  # othermod, webmod
    assert summary["core"] == 0  # core/lib has no .info.yml modules
    assert summary["files"] > 0
    assert len(summary["modules_dirs"]) == 3  # modules, sites/default/modules, web/modules
    assert all(Path(d).is_absolute() for d in summary["modules_dirs"])


def test_index_spans_every_module_location(service: CodebaseService):
    service.refresh()

    names = {m["machine_name"] for m in service.list_modules()}
    assert names == {"mymod", "sitemod", "othermod", "webmod"}


def test_custom_modules_path_is_honored(docroot: Path):
    default_service = CodebaseService(str(docroot))
    default_service.refresh()
    assert "appmod" not in {m["machine_name"] for m in default_service.list_modules()}

    custom_service = CodebaseService(str(docroot), modules_path="apps/modules")
    custom_service.refresh()
    listed = {m["machine_name"]: m["type"] for m in custom_service.list_modules()}
    assert listed["appmod"] == "custom"


def test_paths_lists_root_and_module_dirs(service: CodebaseService):
    result = service.paths()

    assert result["root"] == str(service.root)
    assert len(result["modules"]) == 3
    root = Path(result["root"]).resolve()
    assert all(Path(d).resolve().is_relative_to(root) for d in result["modules"])


# --- search ----------------------------------------------------------------


def test_search_exact_machine_name_ranks_first(service: CodebaseService):
    results = service.search("mymod")

    assert results[0]["machine_name"] == "mymod"
    assert "machine name" in results[0]["reason"]


def test_search_exact_name_beats_description_match(service: CodebaseService):
    # 'other module' is othermod's exact human name, but also appears in
    # mymod's description - the exact match must win.
    results = service.search("other module")
    names = [r["machine_name"] for r in results]

    assert names[0] == "othermod"
    assert "module name" in results[0]["reason"]
    assert "mymod" in names  # description match still surfaces
    assert names.index("mymod") > 0


def test_search_description_match(service: CodebaseService):
    results = service.search("pdf")

    assert [r["machine_name"] for r in results] == ["othermod"]
    assert "description" in results[0]["reason"]


def test_search_scope_filters_module_types(service: CodebaseService):
    custom = service.search("module", scope="custom")
    contrib = service.search("module", scope="contrib")

    assert custom and {r["type"] for r in custom} == {"custom"}
    assert contrib and {r["type"] for r in contrib} == {"contrib"}
    assert service.search("pdf", scope="custom") == []


def test_search_honors_limit_and_empty_query(service: CodebaseService):
    assert len(service.search("module", limit=1)) == 1
    assert service.search("") == []


def test_search_rejects_unknown_scope(service: CodebaseService):
    with pytest.raises(ValueError, match="Unknown scope"):
        service.search("pdf", scope="everything")


def test_search_modules_returns_recommendation_items(service: CodebaseService):
    items = service.search_modules("pdf generation")

    assert items[0]["machine_name"] == "othermod"
    for item in items:
        assert {"machine_name", "name", "type", "reason"} <= set(item)


# --- listing / describe -----------------------------------------------------


def test_list_modules_carries_metadata(service: CodebaseService):
    modules = {m["machine_name"]: m for m in service.list_modules()}

    mymod = modules["mymod"]
    assert mymod["name"] == "My Module"
    assert mymod["type"] == "custom"
    assert mymod["version"] == "1.2.0"
    assert mymod["dependencies"] == ["node", "webmod"]
    assert mymod["description"]
    assert Path(mymod["path"]).name == "mymod"


def test_list_modules_show_unused_marks_candidates(service: CodebaseService):
    modules = {m["machine_name"]: m["unused"] for m in service.list_modules(show_unused=True)}

    assert modules["othermod"] is True  # no hooks, nothing depends on it
    assert modules["mymod"] is False  # implements hooks
    assert modules["sitemod"] is False  # implements hooks
    assert modules["webmod"] is False  # mymod depends on it


def test_describe_returns_the_full_record(service: CodebaseService):
    detail = service.describe("mymod")

    assert detail is not None
    assert detail["name"] == "My Module"
    assert detail["dependencies"] == ["node", "webmod"]
    hook_names = {hook["name"] for hook in detail["hooks"]}
    assert hook_names == {"mymod_form_alter", "mymod_help"}
    assert detail["hooks"][0]["file"] == "mymod.module"
    assert detail["services"][0]["id"] == "mymod.settings"
    assert detail["routes"][0]["name"] == "mymod.settings_form"
    assert detail["classes"][0]["name"] == "Foo"
    assert detail["classes"][0]["file"] == "src/Plugin/Foo.php"
    assert detail["files"] >= 6
    assert [dep["machine_name"] for dep in detail["reverse_dependencies"]] == ["sitemod"]


def test_describe_unknown_module_is_none(service: CodebaseService):
    assert service.describe("no_such_module") is None


# --- unused / redundancy / hooks -------------------------------------------


def test_unused_modules_only_reports_unreferenced_hookless_modules(service: CodebaseService):
    unused = service.unused_modules()

    assert [m["machine_name"] for m in unused] == ["othermod"]
    assert "no hook implementations" in unused[0]["reason"]


def test_redundancy_check_reports_existing_coverage(service: CodebaseService):
    result = service.redundancy_check("pdf generation")

    assert result["matches"][0]["machine_name"] == "othermod"
    assert "Other Module" in result["recommendation"]


def test_redundancy_check_without_matches_says_so(service: CodebaseService):
    result = service.redundancy_check("quantum blockchain sync")

    assert result["matches"] == []
    assert "No existing functionality" in result["recommendation"]


def test_find_hooks_reports_implementations(service: CodebaseService):
    implementations = service.find_hooks("form_alter")

    assert {impl["machine_name"] for impl in implementations} == {"mymod", "sitemod"}
    assert all(impl["file"].endswith(".module") for impl in implementations)
    assert all(isinstance(impl["line"], int) and impl["line"] > 0 for impl in implementations)


def test_find_hooks_accepts_the_hook_prefix(service: CodebaseService):
    implementations = service.find_hooks("hook_help")

    assert [impl["function"] for impl in implementations] == ["mymod_help"]


def test_find_hooks_unknown_hook_is_empty(service: CodebaseService):
    assert service.find_hooks("definitely_not_a_hook") == []


# --- file access and path safety -------------------------------------------


def test_list_files_returns_module_relative_paths(service: CodebaseService):
    files = service.list_files("mymod")

    assert "mymod.module" in files
    assert "mymod.info.yml" in files
    assert "src/Plugin/Foo.php" in files
    assert all(not Path(f).is_absolute() for f in files)
    assert service.list_files("no_such_module") == []


def test_tree_is_nested_and_depth_capped(service: CodebaseService):
    tree = service.tree("mymod")

    assert tree["name"] == "mymod"
    assert tree["type"] == "dir"
    by_name = {child["name"]: child for child in tree["children"]}
    assert by_name["mymod.module"]["type"] == "file"
    assert by_name["big.txt"]["size"] == 70_000
    assert "src" in by_name and by_name["src"]["type"] == "dir"
    plugin_dirs = {child["name"] for child in by_name["src"]["children"]}
    assert "Plugin" in plugin_dirs

    missing = service.tree("no_such_module")
    assert "error" in missing


def test_read_file_returns_content_and_size(service: CodebaseService):
    result = service.read_file("mymod", "mymod.module")

    assert result["path"] == "mymod.module"
    assert result["content"] == MYMOD_MODULE
    assert result["size"] == len(MYMOD_MODULE)
    assert result["truncated"] is False


def test_read_file_truncates_large_files(service: CodebaseService):
    result = service.read_file("mymod", "big.txt")

    assert result["truncated"] is True
    assert result["size"] == 70_000
    assert len(result["content"]) == 64 * 1024


def test_read_file_rejects_absolute_paths(service: CodebaseService):
    assert "error" in service.read_file("mymod", "/etc/passwd")


def test_read_file_rejects_dotdot_traversal(service: CodebaseService):
    assert "error" in service.read_file("mymod", "../othermod/othermod.info.yml")
    assert "error" in service.read_file("mymod", "../../secret.txt")


def test_read_file_rejects_symlinks_escaping_the_root(service: CodebaseService):
    result = service.read_file("mymod", "secret_link.txt")

    assert "error" in result
    assert "TOP SECRET" not in str(result)


def test_read_file_unknown_module_errors(service: CodebaseService):
    assert "error" in service.read_file("no_such_module", "whatever.txt")


def test_read_function_extracts_function_and_docblock(service: CodebaseService):
    result = service.read_function("mymod", "mymod_form_alter")

    assert result is not None
    assert result["path"] == "mymod.module"
    assert isinstance(result["line"], int) and result["line"] > 0
    assert "Implements hook_form_alter()" in result["code"]
    assert "function mymod_form_alter" in result["code"]
    assert result["code"].count("function mymod_form_alter") == 1


def test_read_function_finds_class_methods(service: CodebaseService):
    result = service.read_function("mymod", "build")

    assert result is not None
    assert result["path"] == "src/Plugin/Foo.php"
    assert "public function build" in result["code"]
    assert "Builds the thing." in result["code"]


def test_read_function_unknown_function_is_none(service: CodebaseService):
    assert service.read_function("mymod", "missing_function") is None


# --- tools -----------------------------------------------------------------


def _tool_functions(**deps: Any) -> dict[str, Any]:
    class FakeMCP:
        def __init__(self) -> None:
            self.fns: dict[str, Any] = {}

        def tool(self, *args: Any, **kwargs: Any):
            def decorate(fn):
                self.fns[fn.__name__] = fn
                return fn

            return decorate

    mcp = FakeMCP()
    codebase_tools.register_tools(mcp, **deps)  # type: ignore[arg-type]
    return mcp.fns


def test_all_twelve_codebase_tools_are_registered():
    """The tools must keep their names; an MCP client may hold references."""
    fns = _tool_functions()

    assert sorted(fns) == sorted([
        "codebase_index_refresh",
        "codebase_search",
        "codebase_module_list",
        "codebase_module_describe",
        "codebase_unused_modules",
        "codebase_redundancy_check",
        "codebase_hooks_find",
        "codebase_paths_list",
        "codebase_files_list",
        "codebase_directory_tree",
        "codebase_file_read",
        "codebase_function_read",
    ])


async def test_tools_error_without_a_configured_service():
    fns = _tool_functions()

    for name, args in (
        ("codebase_index_refresh", ()),
        ("codebase_search", ("pdf",)),
        ("codebase_module_list", ()),
        ("codebase_module_describe", ("mymod",)),
        ("codebase_unused_modules", ()),
        ("codebase_redundancy_check", ("pdf",)),
        ("codebase_hooks_find", ("form_alter",)),
        ("codebase_paths_list", ()),
        ("codebase_files_list", ("mymod",)),
        ("codebase_directory_tree", ("mymod",)),
        ("codebase_file_read", ("mymod", "mymod.module")),
        ("codebase_function_read", ("mymod", "mymod_form_alter")),
    ):
        result = await fns[name](*args)
        assert "error" in result, name
        assert "DRUPAL_ROOT" in result["error"], name


async def test_tools_error_when_root_is_not_a_directory(tmp_path: Path):
    fns = _tool_functions(codebase_service=CodebaseService(str(tmp_path / "missing")))

    result = await fns["codebase_search"]("pdf")

    assert "DRUPAL_ROOT" in result["error"]


async def test_tool_happy_path(docroot: Path):
    fns = _tool_functions(codebase_service=CodebaseService(str(docroot)))

    refresh = await fns["codebase_index_refresh"]()
    assert refresh["modules"] == 4
    assert refresh["files"] > 0

    search = await fns["codebase_search"]("pdf")
    assert search["count"] == 1
    assert search["results"][0]["machine_name"] == "othermod"

    listed = await fns["codebase_module_list"](show_unused=True)
    assert listed["count"] == 4

    described = await fns["codebase_module_describe"]("mymod")
    assert described["name"] == "My Module"

    unused = await fns["codebase_unused_modules"]()
    assert [m["machine_name"] for m in unused["modules"]] == ["othermod"]

    redundancy = await fns["codebase_redundancy_check"]("pdf generation")
    assert redundancy["matches"][0]["machine_name"] == "othermod"

    hooks = await fns["codebase_hooks_find"]("form_alter")
    assert hooks["count"] == 2

    paths = await fns["codebase_paths_list"]()
    assert paths["root"] == str(docroot)

    files = await fns["codebase_files_list"]("mymod")
    assert "mymod.module" in files["files"]

    tree = await fns["codebase_directory_tree"]("mymod")
    assert tree["type"] == "dir"

    read = await fns["codebase_file_read"]("mymod", "mymod.module")
    assert "mymod_form_alter" in read["content"]
    assert read["truncated"] is False

    function = await fns["codebase_function_read"]("mymod", "mymod_form_alter")
    assert "hook_form_alter" in function["code"]


async def test_tools_validate_machine_names(docroot: Path):
    fns = _tool_functions(codebase_service=CodebaseService(str(docroot)))

    describe = await fns["codebase_module_describe"]("../evil")
    assert "Invalid module name" in describe["error"]

    hooks = await fns["codebase_hooks_find"]("form alter")
    assert "Invalid hook name" in hooks["error"]

    tree = await fns["codebase_directory_tree"]("my mod")
    assert "Invalid module name" in tree["error"]

    function = await fns["codebase_function_read"]("mymod", "not a function")
    assert "Invalid function name" in function["error"]


async def test_tools_reject_path_escapes(docroot: Path):
    fns = _tool_functions(codebase_service=CodebaseService(str(docroot)))

    absolute = await fns["codebase_file_read"]("mymod", "/etc/passwd")
    assert "error" in absolute

    traversal = await fns["codebase_file_read"]("mymod", "../../secret.txt")
    assert "error" in traversal

    symlink = await fns["codebase_file_read"]("mymod", "secret_link.txt")
    assert "error" in symlink
    assert "TOP SECRET" not in str(symlink)


async def test_tools_reject_bad_arguments(docroot: Path):
    fns = _tool_functions(codebase_service=CodebaseService(str(docroot)))

    scope = await fns["codebase_search"]("pdf", 5, "bogus")
    assert "scope" in scope["error"]

    limit = await fns["codebase_search"]("pdf", 0)
    assert "limit" in limit["error"]

    unknown = await fns["codebase_module_describe"]("no_such_module")
    assert "not in the local index" in unknown["error"]

    missing_function = await fns["codebase_function_read"]("mymod", "missing_function")
    assert "not found" in missing_function["error"]
