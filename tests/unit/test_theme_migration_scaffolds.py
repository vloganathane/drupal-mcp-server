"""Offline tests for the scaffold writers outside ``module_dev``.

Batch one pinned the module scaffolds; this file extends the same rule
to the writers that emit themes, migration plugins, and Behat/Nightwatch
tests. The live sweep proves they answer — never that what they write
can be loaded — and reading them found the same disease:

- ``theme_create`` dumped full library *definitions* into .info.yml's
  ``libraries`` key, which takes a list of library names to attach by
  default: with ``libraries`` passed, the theme's info.yml was
  uninstallable;
- ``generate_module_migration`` wrote ``class Migrate_d7_nodes`` into
  ``migrate_d7_nodes.php`` — class and file disagreeing on case, so
  PSR-4 never autoloads the plugin on a case-sensitive filesystem —
  never imported the ``MigrateSourcePlugin`` annotation it documents
  (discovery fails), and dropped the migrations/ dir, info.yml and
  .module two levels deep inside src/Plugin/ while reporting them at
  the module root.

Batch three completed ``theme_dev`` — the tools the sweep scores OK
because writing *something* is all they were checked for:

- ``theme_settings_form`` generated a class that cannot load on any
  core: ``ConfigFactoryInterface`` and ``ContainerInterface`` used
  unimported, and a constructor override that dropped D11's required
  ``TypedConfigManagerInterface`` while its services.yml entry passed
  only ``@config.factory`` — the container could not build the form
  and ``ConfigFormBaseTrait::config()`` threw on the first build;
- ``theme_debug_enable`` ran three ``config:set twig.config …`` calls
  (one malformed argument string, against a config object that does
  not exist, results discarded) and reported ``twig_debug: True``
  regardless — on every site it ever ran against, nothing changed;
- ``theme_template_override`` silently makedirs'd a half-theme for a
  theme that did not exist, raised an uncaught FileNotFoundError for
  any nested name like ``views/views-view-table.html.twig``, and
  ``os.path.join`` let an absolute ``template_name`` write anywhere;
- ``theme_breakpoint_create`` had no theme-exists guard at all, so a
  missing theme was an uncaught traceback rather than an answer.

Batch four completed ``migration`` — and found the same disease in the
one tool the live sweep scores OK while its create path never runs:

- ``migrate_taxonomy`` branched on ``check.get("error")`` after
  ``get_by_id`` — but the client *raises* (LookupError/HTTPStatusError)
  rather than returning an error dict, so the create branches were
  dead code: a vocabulary or term missing from the target site was
  reported as an error and never created, on every call, forever;
  the caller's ``terms`` list was also forwarded as a vocabulary
  attribute (a 400 on any real update), and the inert
  ``source_jsonapi`` parameter was accepted, checked twice, and never
  used;
- ``generate_migration_yaml`` accepted ``destination`` and ignored it
  (the plugin was hardcoded to entity:node), hand-rolled its YAML so
  any value containing ``": "`` produced an unparseable document, and
  interpolated an unvalidated migration id into config Drupal's
  migrate storage must load;
- ``sync_media_files`` returned a silent ``synced: 0`` for a source
  path that does not exist, raised SameFileError when a directory was
  synced onto itself, and abandoned the whole run on the first
  unreadable file.

Each test pins the shape that was wrong, so none can return silently.
"""

import asyncio
import inspect
from pathlib import Path
from typing import Any

import yaml

from tests.unit.test_tool_utils import _Drush, _register


def _writer(module_name: str, **deps: Any) -> dict[str, Any]:
    """Register a tools module with a drush client that is merely present."""
    deps.setdefault("drush_client", _Drush({"returncode": 0, "data": {}}))
    return _register(module_name, **deps)


def _migration_fns(monkeypatch, tmp_path: Any, **deps: Any) -> dict[str, Any]:
    """Register the migration tools with custom deps.

    MigrationService mkdirs its storage dir at registration, so the env
    var always points it into tmp instead of the repo.
    """
    monkeypatch.setenv("DRUPAL_MCP_MIGRATION_DIR", str(tmp_path / "store"))
    deps.setdefault("drush_client", _Drush({"returncode": 0, "data": {}}))
    return _register("migration", **deps)


# --- theme_create ---------------------------------------------------------


def test_theme_create_writes_a_theme_drupal_can_load(tmp_path) -> None:
    """The default scaffold, and the batch-one rule applied to its
    report: every files_created entry must resolve under the path the
    tool reports."""
    fns = _writer("theme_dev")
    theme = tmp_path / "aurora"

    result = asyncio.run(fns["theme_create"]("Aurora", path=str(theme)))

    assert result["success"] is True
    assert result["machine_name"] == "aurora"
    assert result["path"] == str(theme)

    info = yaml.safe_load((theme / "aurora.info.yml").read_text())
    assert info["type"] == "theme"
    assert info["base theme"] == "stable9"
    assert "content" in info["regions"]
    assert "footer" in info["regions"]

    # The .theme hooks are named for the machine name.
    php = (theme / "aurora.theme").read_text()
    assert "function aurora_theme_suggestions_page_alter(" in php
    assert "function aurora_preprocess_page(" in php

    # Twig braces balance (the sweep's lint tool checks exactly this).
    twig = (theme / "templates" / "page.html.twig").read_text()
    assert twig.count("{{") == twig.count("}}")
    assert (theme / "templates" / "node.html.twig").is_file()
    assert (theme / "aurora.breakpoints.yml").is_file()

    missing = [
        entry
        for entry in result["files_created"]
        if entry and not (theme / entry).is_file()
    ]
    assert missing == [], f"reported files that were never written: {missing}"


def test_theme_create_keeps_library_definitions_out_of_info_yml(tmp_path) -> None:
    """info.yml's ``libraries`` key takes a list of library *names* to
    attach by default. The old code also dumped the full definitions
    dict there — an info.yml Drupal cannot install — while writing the
    same dict to libraries.yml, where definitions belong."""
    fns = _writer("theme_dev")
    theme = tmp_path / "aurora"

    result = asyncio.run(
        fns["theme_create"](
            "Aurora",
            libraries={"aurora/global": {"css": {"component": {"aurora.css": {}}}}},
            path=str(theme),
        )
    )

    info = yaml.safe_load((theme / "aurora.info.yml").read_text())
    assert "libraries" not in info

    libs = yaml.safe_load((theme / "aurora.libraries.yml").read_text())
    assert "aurora/global" in libs
    assert "aurora.libraries.yml" in [entry for entry in result["files_created"] if entry]


def test_theme_create_guards_drush_and_machine_name(tmp_path) -> None:
    no_drush = _register("theme_dev", drush_client=None)
    assert asyncio.run(no_drush["theme_create"]("Aurora")) == {
        "error": "Drush not available"
    }

    fns = _writer("theme_dev")
    result = asyncio.run(fns["theme_create"]("9lives", path=str(tmp_path / "x")))

    assert "Invalid machine name" in result["error"]
    assert not (tmp_path / "x").exists()


# --- generate_module_migration --------------------------------------------


def _migration(
    monkeypatch, tmp_path: Any, drush_result: dict[str, Any]
) -> tuple[dict[str, Any], Any]:
    """Register the migration tools with a canned drush answer.

    MigrationService mkdirs its storage dir at registration, so the
    env var points it into tmp instead of the repo.
    """
    monkeypatch.setenv("DRUPAL_MCP_MIGRATION_DIR", str(tmp_path / "store"))
    drush = _Drush(drush_result)
    return _register("migration", drush_client=drush), drush


def test_generate_module_migration_surfaces_a_failed_drush_generate(
    monkeypatch, tmp_path
) -> None:
    fns, drush = _migration(
        monkeypatch, tmp_path, {"returncode": 1, "data": {"stderr": "no such generator"}}
    )

    result = asyncio.run(fns["generate_module_migration"]("migrate_d7_nodes", "7", "10"))

    assert "Module generation failed" in result["error"]
    assert ("generate", ["module", "migrate_d7_nodes", "--version=10"]) in drush.calls


def test_generate_module_migration_writes_an_autoloadable_plugin(
    monkeypatch, tmp_path
) -> None:
    """PSR-4 both ways round: the class is StudlyCase and the file that
    holds it carries the same name, and the annotation class the
    discovery docblock names is imported."""
    monkeypatch.chdir(tmp_path)
    fns, _drush = _migration(monkeypatch, tmp_path, {"returncode": 0, "data": {}})

    result = asyncio.run(fns["generate_module_migration"]("migrate_d7_nodes", "7", "10"))

    source = tmp_path / "src" / "Plugin" / "migrate" / "source" / "MigrateD7Nodes.php"
    assert source.is_file()
    php = source.read_text()
    assert "class MigrateD7Nodes extends SqlBase" in php
    assert "use Drupal\\migrate\\Annotation\\MigrateSourcePlugin;" in php
    assert "@MigrateSourcePlugin(" in php

    missing = [
        entry
        for entry in result["files_created"]
        if not (tmp_path / entry).is_file()
    ]
    assert missing == [], f"reported files that were never written: {missing}"


def test_generate_module_migration_sidecars_land_at_the_module_root(
    monkeypatch, tmp_path
) -> None:
    """migrations/, the info.yml and the .module belong at the module
    root — where the report says they are and where Drupal looks — not
    inside src/Plugin/."""
    monkeypatch.chdir(tmp_path)
    fns, _drush = _migration(monkeypatch, tmp_path, {"returncode": 0, "data": {}})

    asyncio.run(fns["generate_module_migration"]("migrate_d7_nodes", "7", "10"))

    migration = yaml.safe_load(
        (tmp_path / "migrations" / "migrate_d7_nodes.yml").read_text()
    )
    assert migration["id"] == "migrate_d7_nodes"
    assert migration["source"]["plugin"] == "migrate_d7_nodes"
    assert migration["destination"]["plugin"] == "entity:node"

    info = yaml.safe_load((tmp_path / "migrate_d7_nodes.info.yml").read_text())
    assert info["type"] == "module"
    assert info["core_version_requirement"] == "^10"

    module_php = (tmp_path / "migrate_d7_nodes.module").read_text()
    assert "function migrate_d7_nodes_migrate_api()" in module_php


def test_generate_module_migration_honours_a_module_root_base_path(
    monkeypatch, tmp_path
) -> None:
    """With base_path inside a module, the sidecars follow the module
    root derived from it."""
    monkeypatch.chdir(tmp_path)
    fns, _drush = _migration(monkeypatch, tmp_path, {"returncode": 0, "data": {}})
    base = (
        tmp_path / "modules" / "custom" / "d7_tools"
        / "src" / "Plugin" / "migrate" / "source"
    )

    asyncio.run(fns["generate_module_migration"]("d7_tools", "7", "10", base_path=str(base)))

    root = tmp_path / "modules" / "custom" / "d7_tools"
    assert (base / "D7Tools.php").is_file()
    assert (root / "migrations" / "d7_tools.yml").is_file()
    assert (root / "d7_tools.info.yml").is_file()


# --- test_scaffold_behat --------------------------------------------------


def test_scaffold_behat_writes_the_scenarios_it_was_given(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    fns = _writer("testing")

    result = asyncio.run(
        fns["test_scaffold_behat"](
            "mymodule",
            "Site login",
            scenarios=[
                {
                    "name": "Visitor sees the front page",
                    "steps": [
                        "Given I am on the homepage",
                        'Then I should see "Drupal"',
                    ],
                }
            ],
        )
    )

    feature = tmp_path / "mymodule" / "tests" / "behat" / "site_login.feature"
    assert result["created"] == "mymodule/tests/behat/site_login.feature"
    text = feature.read_text()
    assert text.startswith("Feature: Site login")
    assert "  Scenario: Visitor sees the front page" in text
    # Steps indent under their Scenario.
    assert "    Given I am on the homepage" in text
    assert '    Then I should see "Drupal"' in text


def test_scaffold_behat_writes_a_default_scenario(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    fns = _writer("testing")

    asyncio.run(fns["test_scaffold_behat"]("mymodule", "Smoke"))

    text = (tmp_path / "mymodule" / "tests" / "behat" / "smoke.feature").read_text()
    assert "  Scenario: Basic test" in text
    assert "    Given I am on the homepage" in text


def test_scaffold_behat_refuses_without_drush() -> None:
    fns = _register("testing", drush_client=None)

    result = asyncio.run(fns["test_scaffold_behat"]("mymodule", "Smoke"))

    assert result == {"error": "Drush not available"}


# --- test_scaffold_nightwatch ---------------------------------------------


def test_scaffold_nightwatch_writes_a_loadable_test_module(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    fns = _writer("testing")

    result = asyncio.run(fns["test_scaffold_nightwatch"]("mymodule", "Front page smoke"))

    test_file = tmp_path / "mymodule" / "tests" / "nightwatch" / "front-page-smoke.js"
    assert result["created"] == "mymodule/tests/nightwatch/front-page-smoke.js"
    text = test_file.read_text()
    assert text.startswith("module.exports = {")
    assert "'Front page smoke': function (browser)" in text
    assert ".waitForElementVisible('body')" in text
    assert text.rstrip().endswith("};")


def test_scaffold_nightwatch_runs_the_steps_it_was_given(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    fns = _writer("testing")

    asyncio.run(
        fns["test_scaffold_nightwatch"](
            "mymodule", "Login", test_steps=["browser.url('/user/login').waitForElementVisible('form')"]
        )
    )

    text = (
        tmp_path / "mymodule" / "tests" / "nightwatch" / "login.js"
    ).read_text()
    assert "    browser.url('/user/login').waitForElementVisible('form')" in text
    # Caller-supplied steps replace the default chain.
    assert "launchUrl" not in text


def test_scaffold_nightwatch_refuses_without_drush() -> None:
    fns = _register("testing", drush_client=None)

    result = asyncio.run(fns["test_scaffold_nightwatch"]("mymodule", "Smoke"))

    assert result == {"error": "Drush not available"}


# --- theme_library_create -------------------------------------------------


def test_theme_library_create_writes_the_definition_into_libraries_yml(tmp_path) -> None:
    fns = _writer("theme_dev")
    theme = tmp_path / "aurora"
    asyncio.run(fns["theme_create"]("Aurora", path=str(theme)))

    result = asyncio.run(
        fns["theme_library_create"](
            "aurora",
            "aurora/global",
            css={"component": {"aurora.css": {}}},
            js={"footer": {"aurora.js": {}}},
            dependencies=["core/drupalSettings"],
            path=str(theme),
        )
    )

    assert result["success"] is True
    libs = yaml.safe_load((theme / "aurora.libraries.yml").read_text())
    assert libs["aurora/global"]["css"] == {"component": {"aurora.css": {}}}
    assert libs["aurora/global"]["js"] == {"footer": {"aurora.js": {}}}
    assert libs["aurora/global"]["dependencies"] == ["core/drupalSettings"]
    assert result["library_definition"] == libs["aurora/global"]


def test_theme_library_create_merges_with_what_is_already_there(tmp_path) -> None:
    fns = _writer("theme_dev")
    theme = tmp_path / "aurora"
    asyncio.run(fns["theme_create"]("Aurora", path=str(theme)))

    asyncio.run(fns["theme_library_create"]("aurora", "aurora/one", path=str(theme)))
    asyncio.run(fns["theme_library_create"]("aurora", "aurora/two", path=str(theme)))

    libs = yaml.safe_load((theme / "aurora.libraries.yml").read_text())
    assert sorted(libs) == ["aurora/one", "aurora/two"]


def test_theme_library_create_refuses_a_theme_that_is_not_there(tmp_path) -> None:
    fns = _writer("theme_dev")

    result = asyncio.run(
        fns["theme_library_create"]("ghost", "ghost/lib", path=str(tmp_path / "ghost"))
    )

    assert "Theme not found" in result["error"]
    assert not (tmp_path / "ghost").exists()


# --- theme_region_create --------------------------------------------------


def test_theme_region_create_adds_a_region_and_keeps_the_others(tmp_path) -> None:
    fns = _writer("theme_dev")
    theme = tmp_path / "aurora"
    asyncio.run(fns["theme_create"]("Aurora", path=str(theme)))

    result = asyncio.run(
        fns["theme_region_create"]("aurora", "hero", "Hero band", path=str(theme))
    )

    assert result["success"] is True
    info = yaml.safe_load((theme / "aurora.info.yml").read_text())
    assert info["regions"]["hero"] == "Hero band"
    # The default regions survive an edit of the same file.
    assert info["regions"]["content"] == "Content"
    assert result["all_regions"]["hero"] == "Hero band"


def test_theme_region_create_refuses_without_an_info_file(tmp_path) -> None:
    fns = _writer("theme_dev")
    ghost = tmp_path / "ghost"
    ghost.mkdir()

    result = asyncio.run(fns["theme_region_create"]("ghost", "hero", "Hero", path=str(ghost)))

    assert "info file not found" in result["error"]


# --- theme_template_override ----------------------------------------------


def test_theme_template_override_writes_the_supplied_content(tmp_path) -> None:
    fns = _writer("theme_dev")
    theme = tmp_path / "aurora"
    asyncio.run(fns["theme_create"]("Aurora", path=str(theme)))

    result = asyncio.run(
        fns["theme_template_override"](
            "aurora", "views-view--foo.html.twig", "{{ content['#rows'] }}", path=str(theme)
        )
    )

    written = theme / "templates" / "views-view--foo.html.twig"
    assert result["template_file"] == str(written)
    assert written.read_text() == "{{ content['#rows'] }}"


def test_theme_template_override_generates_default_content_by_prefix(tmp_path) -> None:
    fns = _writer("theme_dev")
    theme = tmp_path / "aurora"
    asyncio.run(fns["theme_create"]("Aurora", path=str(theme)))

    for name, marker in [
        ("page.html.twig", "{{ page_top }}"),
        ("node.html.twig", "{{ node.label }}"),
        ("block.html.twig", "{{ content_attributes }}"),
        ("anything.html.twig", "{{ content }}"),
    ]:
        asyncio.run(fns["theme_template_override"]("aurora", name, path=str(theme)))
        text = (theme / "templates" / name).read_text()
        assert marker in text, f"{name} is missing {marker}"
        # The sweep's own lint tool checks exactly this.
        assert text.count("{{") == text.count("}}")

    # Only the page stub is a full document.
    assert "<!DOCTYPE html>" in (theme / "templates" / "page.html.twig").read_text()
    assert "<!DOCTYPE html>" not in (theme / "templates" / "node.html.twig").read_text()


def test_theme_template_override_refuses_a_theme_that_is_not_there(tmp_path) -> None:
    """It used to makedirs a stray templates/ tree for a theme that does
    not exist, leaving a half-theme behind."""
    fns = _writer("theme_dev")
    ghost = tmp_path / "ghost"

    result = asyncio.run(fns["theme_template_override"]("ghost", "page.html.twig", path=str(ghost)))

    assert "Theme not found" in result["error"]
    assert not ghost.exists()


def test_theme_template_override_creates_subdirectories_for_nested_names(tmp_path) -> None:
    """Views overrides live in templates/views/. The old open() raised
    FileNotFoundError uncaught for any nested name."""
    fns = _writer("theme_dev")
    theme = tmp_path / "aurora"
    asyncio.run(fns["theme_create"]("Aurora", path=str(theme)))

    result = asyncio.run(
        fns["theme_template_override"](
            "aurora", "views/views-view-table.html.twig", "{{ content }}", path=str(theme)
        )
    )

    written = theme / "templates" / "views" / "views-view-table.html.twig"
    assert result["template_file"] == str(written)
    assert written.is_file()


def test_theme_template_override_refuses_to_write_outside_the_theme(tmp_path) -> None:
    """os.path.join discards the templates dir when template_name is
    absolute, and `..` climbs out of it: the tool would write anywhere
    the server process can."""
    fns = _writer("theme_dev")
    theme = tmp_path / "aurora"
    asyncio.run(fns["theme_create"]("Aurora", path=str(theme)))

    absolute = asyncio.run(
        fns["theme_template_override"](
            "aurora", str(tmp_path / "escape.html.twig"), "x", path=str(theme)
        )
    )
    climbing = asyncio.run(
        fns["theme_template_override"]("aurora", "../../escape.html.twig", "x", path=str(theme))
    )

    assert "inside the theme's templates/" in absolute["error"]
    assert "inside the theme's templates/" in climbing["error"]
    assert not (tmp_path / "escape.html.twig").exists()


# --- theme_preprocess_function --------------------------------------------


def test_theme_preprocess_function_appends_to_the_theme_file(tmp_path) -> None:
    fns = _writer("theme_dev")
    theme = tmp_path / "aurora"
    asyncio.run(fns["theme_create"]("Aurora", path=str(theme)))
    original = (theme / "aurora.theme").read_text()

    result = asyncio.run(
        fns["theme_preprocess_function"](
            "aurora", "node", "$variables['demo'] = TRUE;", path=str(theme)
        )
    )

    assert result["success"] is True
    php = (theme / "aurora.theme").read_text()
    # Appended, never rewritten.
    assert php.startswith(original)
    assert "function aurora_preprocess_node(&$variables) {" in php
    assert "$variables['demo'] = TRUE;" in php
    assert "Implements hook_preprocess_node()." in php


def test_theme_preprocess_function_refuses_without_a_theme_file(tmp_path) -> None:
    fns = _writer("theme_dev")

    result = asyncio.run(
        fns["theme_preprocess_function"]("ghost", "node", "$x = 1;", path=str(tmp_path / "ghost"))
    )

    assert "Theme file not found" in result["error"]


# --- theme_breakpoint_create ----------------------------------------------


def test_theme_breakpoint_create_merges_into_breakpoints_yml(tmp_path) -> None:
    fns = _writer("theme_dev")
    theme = tmp_path / "aurora"
    asyncio.run(fns["theme_create"]("Aurora", path=str(theme)))

    result = asyncio.run(
        fns["theme_breakpoint_create"](
            "aurora",
            "aurora.wide",
            "Wide",
            "(min-width: 1600px)",
            weight=3,
            multipliers=["1x", "2x"],
            path=str(theme),
        )
    )

    assert result["success"] is True
    bp = yaml.safe_load((theme / "aurora.breakpoints.yml").read_text())
    assert bp["aurora.wide"] == {
        "label": "Wide",
        "mediaQuery": "(min-width: 1600px)",
        "weight": 3,
        "multipliers": ["1x", "2x"],
    }
    # theme_create's defaults survive the merge.
    assert "aurora.mobile" in bp


def test_theme_breakpoint_create_refuses_a_theme_that_is_not_there(tmp_path) -> None:
    """No guard meant open() raised FileNotFoundError uncaught — the only
    answer an MCP client saw was a traceback."""
    fns = _writer("theme_dev")

    result = asyncio.run(
        fns["theme_breakpoint_create"](
            "ghost", "ghost.narrow", "Narrow", "(max-width: 400px)", path=str(tmp_path / "ghost")
        )
    )

    assert "Theme not found" in result["error"]
    assert not (tmp_path / "ghost").exists()


# --- theme_base_change ----------------------------------------------------


def test_theme_base_change_swaps_the_base_theme(tmp_path) -> None:
    fns = _writer("theme_dev")
    theme = tmp_path / "aurora"
    asyncio.run(fns["theme_create"]("Aurora", path=str(theme)))

    result = asyncio.run(fns["theme_base_change"]("aurora", "olivero", path=str(theme)))

    assert result["old_base_theme"] == "stable9"
    assert result["new_base_theme"] == "olivero"
    info = yaml.safe_load((theme / "aurora.info.yml").read_text())
    assert info["base theme"] == "olivero"


def test_theme_base_change_refuses_without_an_info_file(tmp_path) -> None:
    fns = _writer("theme_dev")

    result = asyncio.run(fns["theme_base_change"]("ghost", "olivero", path=str(tmp_path / "ghost")))

    assert "info file not found" in result["error"]


# --- theme_settings_form --------------------------------------------------


def test_theme_settings_form_generates_a_class_that_can_be_loaded(tmp_path) -> None:
    """Ground truth, core 11.4 (the local drupal-live tree): the trait
    ConfigFormBaseTrait declares ``abstract protected function
    getEditableConfigNames()`` — non-static — and ConfigFormBase's
    constructor takes ``(ConfigFactoryInterface, TypedConfigManagerInterface)``
    with no create() to inherit. The old generator used
    ConfigFactoryInterface and ContainerInterface unimported (a fatal on
    any core) and overrode the constructor with one argument, so the
    typed property stayed uninitialized and the very first
    ``$this->config()`` threw 'No config factory available'."""
    fns = _writer("theme_dev")
    theme = tmp_path / "aurora"
    asyncio.run(fns["theme_create"]("Aurora", path=str(theme)))

    result = asyncio.run(
        fns["theme_settings_form"](
            "aurora",
            settings={"logo_width": {"type": "number", "title": "Logo width", "default": 120}},
            path=str(theme),
        )
    )

    assert result["success"] is True
    php = (theme / "src" / "Form" / "ThemeSettingsForm.php").read_text()

    # Non-static, matching the trait on core 10 and 11 alike.
    assert "protected function getEditableConfigNames() {" in php
    assert "protected static function getEditableConfigNames" not in php
    # No constructor override: one create() serving both majors passes
    # both services (D10's one-argument constructor ignores the extra).
    assert "__construct" not in php
    assert "$container->get('config.factory')" in php
    assert "$container->get('config.typed')" in php
    # Every unqualified class in a signature is imported.
    assert "use Drupal\\Core\\Form\\ConfigFormBase;" in php
    assert "use Drupal\\Core\\Form\\FormStateInterface;" in php
    assert "use Symfony\\Component\\DependencyInjection\\ContainerInterface;" in php
    # The caller's setting round-trips through build and submit.
    assert "'#type' => 'number'" in php
    assert "$config->get('logo_width') ?? '120'" in php
    assert "$config->set('logo_width', $form_state->getValue('logo_width'));" in php


def test_theme_settings_form_wires_routing_and_a_service_the_container_can_build(
    tmp_path,
) -> None:
    fns = _writer("theme_dev")
    theme = tmp_path / "aurora"
    asyncio.run(fns["theme_create"]("Aurora", path=str(theme)))

    asyncio.run(fns["theme_settings_form"]("aurora", path=str(theme)))

    routing = yaml.safe_load((theme / "aurora.routing.yml").read_text())
    route = routing["aurora.theme_settings"]
    assert route["path"] == "/admin/appearance/settings/aurora"
    assert route["defaults"]["_form"] == "\\Drupal\\aurora\\Form\\ThemeSettingsForm"
    assert route["requirements"]["_permission"] == "administer themes"

    services = yaml.safe_load((theme / "aurora.services.yml").read_text())
    service = services["services"]["aurora.theme_settings_form"]
    # services.yml class: ids carry no leading backslash, as in core.services.yml.
    assert service["class"] == "Drupal\\aurora\\Form\\ThemeSettingsForm"
    # D11's ConfigFormBase constructor requires the typed config manager;
    # registered with only @config.factory the service cannot be built.
    assert service["arguments"] == ["@config.factory", "@config.typed"]


def test_theme_settings_form_reports_paths_that_exist_and_refuses_a_missing_theme(
    tmp_path,
) -> None:
    fns = _writer("theme_dev")
    theme = tmp_path / "aurora"
    asyncio.run(fns["theme_create"]("Aurora", path=str(theme)))

    result = asyncio.run(fns["theme_settings_form"]("aurora", path=str(theme)))

    assert Path(result["form_file"]).is_file()

    ghost = tmp_path / "ghost"
    refused = asyncio.run(fns["theme_settings_form"]("ghost", path=str(ghost)))
    assert "Theme not found" in refused["error"]
    assert not ghost.exists()


# --- theme_asset_optimize -------------------------------------------------


def test_theme_asset_optimize_runs_the_system_performance_commands() -> None:
    drush = _Drush({"returncode": 0, "data": {}, "stderr": ""})
    fns = _register("theme_dev", drush_client=drush)

    result = asyncio.run(fns["theme_asset_optimize"]("aurora"))

    assert drush.calls == [
        ("config:set", ["system.performance", "css.preprocess", "1"]),
        ("config:set", ["system.performance", "js.preprocess", "1"]),
        ("config:set", ["system.performance", "css.gzip", "1"]),
        ("config:set", ["system.performance", "js.gzip", "1"]),
    ]
    assert result["success"] is True
    assert result["optimizations"] == {"css": True, "js": True, "aggregate": True}


def test_theme_asset_optimize_honours_the_flags() -> None:
    drush = _Drush({"returncode": 0, "data": {}, "stderr": ""})
    fns = _register("theme_dev", drush_client=drush)

    asyncio.run(fns["theme_asset_optimize"]("aurora", optimize_js=False, aggregate=False))

    assert drush.calls == [("config:set", ["system.performance", "css.preprocess", "1"])]


def test_theme_asset_optimize_surfaces_a_failed_command() -> None:
    """It reported success:True whatever drush answered, so a site where
    config:set failed read as optimized."""
    drush = _Drush({
        "returncode": 1,
        "data": {},
        "stderr": "Config system.performance has no key css.preprocess",
        "command": "drush config:set system.performance css.preprocess 1",
    })
    fns = _register("theme_dev", drush_client=drush)

    result = asyncio.run(fns["theme_asset_optimize"]("aurora", aggregate=False))

    assert "error" in result
    assert "has no key css.preprocess" in result["error"]
    assert result["success"] is False


# --- theme_debug_enable ---------------------------------------------------


def test_theme_debug_enable_refuses_instead_of_reporting_a_change_it_cannot_make() -> None:
    """Three `config:set twig.config …` calls — one malformed argument
    string, aimed at a config object that does not exist, results
    discarded — while the payload claimed twig_debug:True. Twig debug is
    a container parameter (core/services.yml `twig.config`), reachable
    only through settings.php; no config:set ever moved it."""
    drush = _Drush({"returncode": 0, "data": {}, "stderr": ""})
    fns = _register("theme_dev", drush_client=drush)

    result = asyncio.run(fns["theme_debug_enable"]("aurora"))

    assert "error" in result
    assert "container parameter" in result["error"]
    assert "settings.php" in result["error"]
    # Nothing was run against the site, and nothing pretends otherwise.
    assert drush.calls == []
    assert "debug_enabled" not in result
    assert "twig_debug" not in result


# --- theme_lint_twig ------------------------------------------------------


def test_theme_lint_twig_passes_a_clean_theme(tmp_path) -> None:
    fns = _writer("theme_dev")
    theme = tmp_path / "aurora"
    asyncio.run(fns["theme_create"]("Aurora", path=str(theme)))

    result = asyncio.run(fns["theme_lint_twig"]("aurora", path=str(theme)))

    assert result["success"] is True
    assert result["files_checked"] == 3
    assert result["errors"] == []


def test_theme_lint_twig_names_the_file_that_does_not_balance(tmp_path) -> None:
    fns = _writer("theme_dev")
    theme = tmp_path / "aurora"
    asyncio.run(fns["theme_create"]("Aurora", path=str(theme)))
    broken = theme / "templates" / "broken.html.twig"
    broken.write_text("{{ orphan }} {% if x")

    result = asyncio.run(fns["theme_lint_twig"]("aurora", path=str(theme)))

    assert result["files_checked"] == 4
    files = [entry["file"] for entry in result["errors"]]
    assert str(broken) in files
    # Each error names its own problem: the braces still balance here.
    messages = " ".join(entry["error"] for entry in result["errors"])
    assert "Unbalanced {% %} tags" in messages
    assert "Unbalanced {{ }} braces" not in messages


def test_theme_lint_twig_refuses_without_a_templates_dir(tmp_path) -> None:
    fns = _writer("theme_dev")

    result = asyncio.run(fns["theme_lint_twig"]("ghost", path=str(tmp_path / "ghost")))

    assert "Templates directory not found" in result["error"]


# --- generate_migration_yaml ------------------------------------------------


def test_generate_migration_yaml_honours_the_destination_it_was_given(
    monkeypatch, tmp_path
) -> None:
    """``destination`` was accepted and ignored — the plugin was hardcoded
    to entity:node — so every generated file targeted nodes whatever the
    caller asked the tool to write."""
    fns = _migration_fns(monkeypatch, tmp_path)

    result = asyncio.run(
        fns["generate_migration_yaml"](
            "users_from_d7",
            source={"plugin": "d7_user"},
            destination={"plugin": "entity:user", "default_bundle": "customer"},
        )
    )

    config = yaml.safe_load(result["yaml"])
    assert config["id"] == "users_from_d7"
    assert config["source"]["plugin"] == "d7_user"
    # The tool's documented default, not the caller's plugin, overwritten.
    assert config["source"]["key"] == "default"
    assert config["destination"] == {"plugin": "entity:user", "default_bundle": "customer"}


def test_generate_migration_yaml_survives_values_containing_colons(
    monkeypatch, tmp_path
) -> None:
    """Hand-rolled f-string YAML broke on any value containing ': ':
    ``plugin: d7_node: legacy`` is not parseable, so the document this
    tool exists to produce could not be loaded by anyone who called it."""
    fns = _migration_fns(monkeypatch, tmp_path)

    result = asyncio.run(
        fns["generate_migration_yaml"](
            "legacy_nodes",
            source={"plugin": "d7_node: legacy"},
            destination={"plugin": "entity:node", "default_bundle": "news: fresh"},
        )
    )

    config = yaml.safe_load(result["yaml"])
    assert config["source"]["plugin"] == "d7_node: legacy"
    assert config["destination"]["default_bundle"] == "news: fresh"


def test_generate_migration_yaml_rejects_an_id_that_is_not_a_machine_name(
    monkeypatch, tmp_path
) -> None:
    """The id is config Drupal's migrate storage must load, and it was
    interpolated unvalidated: 'my migration' is invalid config, and a
    value carrying a newline injects keys into the very document this
    tool emits."""
    fns = _migration_fns(monkeypatch, tmp_path)

    refused = asyncio.run(fns["generate_migration_yaml"]("my migration", {}, {}))
    assert "error" in refused
    assert "yaml" not in refused

    # A machine name still round-trips.
    accepted = asyncio.run(fns["generate_migration_yaml"]("d7_nodes", {}, {}))
    assert yaml.safe_load(accepted["yaml"])["id"] == "d7_nodes"


# --- run_migration_test / validate / rollback -------------------------------


def test_run_migration_test_runs_a_real_command_and_surfaces_failure(
    monkeypatch, tmp_path
) -> None:
    """Drush 13's import command (MigrateRunnerCommands registers
    migrate:import with the dash form as an official alias) and --limit
    are real; a failed run answers with the stderr, not an exit code."""
    fns, drush = _migration(
        monkeypatch,
        tmp_path,
        {
            "returncode": 1,
            "data": {},
            "stderr": "The following modules are required: migrate",
        },
    )

    result = asyncio.run(fns["run_migration_test"]("d7_nodes", limit=5))

    assert drush.calls == [("migrate-import", ["--limit=5", "d7_nodes"])]
    assert "error" in result
    assert "modules are required" in result["error"]
    assert result["migration_id"] == "d7_nodes"


def test_validate_migration_reports_the_status_drush_returned(
    monkeypatch, tmp_path
) -> None:
    fns, drush = _migration(
        monkeypatch, tmp_path, {"returncode": 0, "data": {"d7_nodes": {"status": "completed"}}}
    )

    result = asyncio.run(fns["validate_migration"]("d7_nodes"))

    assert drush.calls == [("migrate-status", ["d7_nodes"])]
    assert result["status"] == {"d7_nodes": {"status": "completed"}}
    assert "error" not in result


def test_rollback_migration_reports_both_outcomes(monkeypatch, tmp_path) -> None:
    fns, drush = _migration(monkeypatch, tmp_path, {"returncode": 0, "data": {}})

    success = asyncio.run(fns["rollback_migration"]("d7_nodes"))

    assert drush.calls == [("migrate-rollback", ["d7_nodes"])]
    assert success["rolled_back"] is True
    assert "error" not in success

    fns, _ = _migration(
        monkeypatch,
        tmp_path,
        {"returncode": 1, "data": {}, "stderr": "Migration d7_nodes did not exist"},
    )
    failed = asyncio.run(fns["rollback_migration"]("d7_nodes"))

    assert failed["rolled_back"] is False
    assert "did not exist" in failed["error"]


# --- sync_media_files -------------------------------------------------------


def test_sync_media_files_copies_the_files_it_finds(monkeypatch, tmp_path) -> None:
    fns = _migration_fns(monkeypatch, tmp_path)
    src = tmp_path / "media"
    (src / "nested").mkdir(parents=True)
    (src / "a.jpg").write_text("A")
    (src / "b.jpg").write_text("B")
    dst = tmp_path / "mirror"

    result = asyncio.run(fns["sync_media_files"](str(src), str(dst)))

    assert result["synced_files"] == 2
    assert "error" not in result
    assert (dst / "a.jpg").read_text() == "A"
    assert (dst / "b.jpg").read_text() == "B"


def test_sync_media_files_refuses_a_source_path_that_does_not_exist(
    monkeypatch, tmp_path
) -> None:
    """A silent ``synced: 0`` made a typo'd path look like a source
    directory that simply held no files."""
    fns = _migration_fns(monkeypatch, tmp_path)
    src = tmp_path / "ghost"
    dst = tmp_path / "dst"

    result = asyncio.run(fns["sync_media_files"](str(src), str(dst)))

    assert "error" in result
    assert "Source path not found" in result["error"]
    # A refused sync creates nothing on either side.
    assert not dst.exists()


def test_sync_media_files_syncs_a_directory_onto_itself_without_raising(
    monkeypatch, tmp_path
) -> None:
    """copy2(src, src) raised SameFileError, which escaped uncaught: the
    run aborted mid-list and the files after the first were never
    counted or copied."""
    fns = _migration_fns(monkeypatch, tmp_path)
    media = tmp_path / "media"
    media.mkdir()
    (media / "a.jpg").write_text("A")

    result = asyncio.run(fns["sync_media_files"](str(media), str(media)))

    assert "error" not in result
    assert result["synced_files"] == 0
    assert result.get("skipped_files") == 1
    assert (media / "a.jpg").read_text() == "A"


def test_sync_media_files_collects_a_copy_failure_and_keeps_going(
    monkeypatch, tmp_path
) -> None:
    """One unreadable file used to abandon the whole run — every file
    after it went unsynced with no answer about why."""
    import shutil as _shutil

    from drupal_mcp_server.tools import migration as migration_mod

    fns = _migration_fns(monkeypatch, tmp_path)
    src = tmp_path / "media"
    src.mkdir()
    (src / "a.jpg").write_text("A")
    (src / "b.jpg").write_text("B")
    dst = tmp_path / "dst"

    real_copy = _shutil.copy2

    def copy_or_fail(source, destination, *args, **kwargs):
        if str(source).endswith("a.jpg"):
            raise PermissionError("a.jpg is locked")
        return real_copy(source, destination, *args, **kwargs)

    monkeypatch.setattr(migration_mod.shutil, "copy2", copy_or_fail)

    result = asyncio.run(fns["sync_media_files"](str(src), str(dst)))

    assert result["synced_files"] == 1
    assert (dst / "b.jpg").exists()
    errors = result["errors"]
    assert [e["file"] for e in errors] == ["a.jpg"]
    assert "locked" in errors[0]["error"]


# --- migrate_taxonomy -------------------------------------------------------


class _JSONAPI:
    """The real client's contract: ``get_by_id`` answers with the resource
    or raises LookupError for a missing id — it never returns an error
    dict, which is exactly what the old branch-on-``error`` code assumed."""

    def __init__(self, existing: tuple[str, ...] = ()) -> None:
        self.existing = set(existing)
        self.created: list[tuple[str, dict[str, Any]]] = []
        self.updated: list[tuple[str, str, dict[str, Any]]] = []

    async def get_by_id(
        self, resource_type: str, uuid: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if f"{resource_type}|{uuid}" in self.existing:
            return {"id": str(uuid), "type": resource_type}
        raise LookupError(f"No resource of type {resource_type!r} with id {uuid!r}")

    async def create_resource(
        self, resource_type: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        self.created.append((resource_type, dict(data)))
        return dict(data)

    async def update_resource(
        self, resource_type: str, uuid: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        self.updated.append((resource_type, uuid, dict(data)))
        return dict(data)


def test_migrate_taxonomy_creates_a_vocabulary_the_target_site_lacks(
    monkeypatch, tmp_path
) -> None:
    """The tool branched on ``check.get("error")`` after get_by_id — but
    the client raises LookupError instead of returning an error dict, so
    the create branch was dead code: a vocabulary missing from the target
    site was reported as an error and never created, on every call."""
    api = _JSONAPI()
    fns = _migration_fns(monkeypatch, tmp_path, jsonapi_client=api)

    result = asyncio.run(
        fns["migrate_taxonomy"](
            [
                {
                    "vid": "topics",
                    "name": "Topics",
                    "description": "Old topics",
                    "terms": [{"tid": "7", "name": "News"}],
                }
            ]
        )
    )

    resources = [resource for resource, _ in api.created]
    assert "taxonomy_vocabulary" in resources, "missing vocabulary was never created"
    assert "taxonomy_term--topics" in resources, "missing term was never created"
    payload = api.created[0][1]
    assert payload["vid"] == "topics"
    assert payload["name"] == "Topics"
    assert result["vocabularies_migrated"] == 1
    assert result["terms_migrated"] == 1
    assert result["errors"] == []


def test_migrate_taxonomy_update_payload_leaves_the_terms_out(
    monkeypatch, tmp_path
) -> None:
    """The raw caller dict was passed to update_resource, so its ``terms``
    list went up as a vocabulary attribute — a 400 on every real update
    path Drupal serves."""
    api = _JSONAPI(existing={"taxonomy_vocabulary|topics"})
    fns = _migration_fns(monkeypatch, tmp_path, jsonapi_client=api)

    result = asyncio.run(
        fns["migrate_taxonomy"](
            [{"vid": "topics", "name": "Topics (new)", "terms": [{"tid": "7", "name": "News"}]}]
        )
    )

    assert api.updated, "existing vocabulary was never updated"
    resource, uuid, payload = api.updated[0]
    assert (resource, uuid) == ("taxonomy_vocabulary", "topics")
    assert "terms" not in payload
    assert payload["name"] == "Topics (new)"
    assert result["vocabularies_migrated"] == 1
    assert result["errors"] == []


def test_migrate_taxonomy_creates_a_missing_term_without_faking_its_tid(
    monkeypatch, tmp_path
) -> None:
    """tid is a read-only identifier: JSON:API resolves it for reads and
    updates but refuses it as a settable attribute, so sending it in a
    create guaranteed a 400. The existence check carried the same dead
    branch as the vocabulary — the term was never created at all."""
    api = _JSONAPI(existing={"taxonomy_vocabulary|topics"})
    fns = _migration_fns(monkeypatch, tmp_path, jsonapi_client=api)

    result = asyncio.run(
        fns["migrate_taxonomy"](
            [{"vid": "topics", "name": "Topics", "terms": [{"tid": "7", "name": "News", "weight": 2}]}]
        )
    )

    term_creates = [
        (resource, data) for resource, data in api.created if resource == "taxonomy_term--topics"
    ]
    assert term_creates, "missing term was never created"
    payload = term_creates[0][1]
    assert "tid" not in payload
    assert payload["name"] == "News"
    assert payload["weight"] == 2
    assert result["terms_migrated"] == 1
    assert result["errors"] == []


def test_migrate_taxonomy_reports_an_unidentifiable_vocabulary_and_keeps_going(
    monkeypatch, tmp_path
) -> None:
    api = _JSONAPI()
    fns = _migration_fns(monkeypatch, tmp_path, jsonapi_client=api)

    result = asyncio.run(
        fns["migrate_taxonomy"]([{"name": "No id"}, {"vid": "topics", "name": "Topics"}])
    )

    assert [e["error"] for e in result["errors"]] == ["Missing vid/id"]
    assert result["vocabularies_processed"] == 2
    assert result["vocabularies_migrated"] == 1
    assert api.created


def test_migrate_taxonomy_has_no_inert_source_jsonapi_parameter(
    monkeypatch, tmp_path
) -> None:
    """``source_jsonapi`` was accepted, checked twice in the guard, and
    never read again — a parameter promising source-site migration that
    did nothing. The honest surface is one JSON:API client, and the
    guard says so exactly once."""
    fns = _migration_fns(monkeypatch, tmp_path)

    assert "source_jsonapi" not in inspect.signature(fns["migrate_taxonomy"]).parameters
    assert asyncio.run(fns["migrate_taxonomy"]([])) == {
        "error": "JSON:API client not available"
    }


# --- migration plan service wrappers ----------------------------------------


class _PlanService:
    """Records delegation instead of touching storage."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.plan_error: dict[str, Any] | None = None

    def _answer(self, name: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((name, kwargs))
        return {"delegated": name, **kwargs}

    def get_plan(self, migration_id: str) -> dict[str, Any]:
        if self.plan_error is not None:
            self.calls.append(("get_plan", {"migration_id": migration_id}))
            return dict(self.plan_error)
        return self._answer("get_plan", migration_id=migration_id)

    def list_plans(self) -> list[dict[str, Any]]:
        return [self._answer("list_plans")]

    def migration_status(self, migration_id: str) -> dict[str, Any]:
        return self._answer("migration_status", migration_id=migration_id)

    def record_entity_result(self, **kwargs: Any) -> dict[str, Any]:
        return self._answer("record_entity_result", **kwargs)

    async def reconcile_counts(self, **kwargs: Any) -> dict[str, Any]:
        return self._answer("reconcile_counts", **kwargs)

    async def run_migration_wave(self, **kwargs: Any) -> dict[str, Any]:
        return self._answer("run_migration_wave", **kwargs)

    async def run_migration(self, **kwargs: Any) -> dict[str, Any]:
        return self._answer("run_migration", **kwargs)


def test_plan_read_wrappers_delegate_verbatim(monkeypatch, tmp_path) -> None:
    service = _PlanService()
    fns = _migration_fns(monkeypatch, tmp_path, migration_service=service)

    plan = asyncio.run(fns["get_migration_plan"]("d7_upgrade"))
    plans = asyncio.run(fns["list_migration_plans"]())
    status = asyncio.run(fns["migration_status"]("d7_upgrade"))

    assert plan["delegated"] == "get_plan"
    assert plans == [{"delegated": "list_plans"}]
    assert status["delegated"] == "migration_status"
    assert service.calls == [
        ("get_plan", {"migration_id": "d7_upgrade"}),
        ("list_plans", {}),
        ("migration_status", {"migration_id": "d7_upgrade"}),
    ]

    # A refusal from the service reaches the caller untouched.
    service.plan_error = {"error": "Migration plan not found: nope"}
    refused = asyncio.run(fns["get_migration_plan"]("nope"))
    assert refused == {"error": "Migration plan not found: nope"}


def test_record_migration_result_passes_every_outcome_field(
    monkeypatch, tmp_path
) -> None:
    service = _PlanService()
    fns = _migration_fns(monkeypatch, tmp_path, migration_service=service)

    result = asyncio.run(
        fns["record_migration_result"](
            "d7_upgrade", "node", "42", target_id="17", status="failed",
            error="403 on POST",
        )
    )

    assert service.calls == [
        (
            "record_entity_result",
            {
                "migration_id": "d7_upgrade",
                "entity_type": "node",
                "legacy_id": "42",
                "target_id": "17",
                "status": "failed",
                "error": "403 on POST",
            },
        )
    ]
    assert result["delegated"] == "record_entity_result"


def test_wave_and_reconcile_pass_credentials_and_mapping_through(
    monkeypatch, tmp_path
) -> None:
    service = _PlanService()
    fns = _migration_fns(monkeypatch, tmp_path, migration_service=service)

    asyncio.run(
        fns["run_migration_wave"](
            "d7_upgrade",
            "node--article",
            batch_size=25,
            dry_run=True,
            source_token="tok",
            verify_tls=False,
            source_username="admin",
            source_password="pw",
            field_mapping={"title": "field_headline"},
        )
    )
    asyncio.run(fns["reconcile_migration_counts"]("d7_upgrade", ["node--article", "user--user"]))

    assert service.calls[0] == (
        "run_migration_wave",
        {
            "migration_id": "d7_upgrade",
            "resource_type": "node--article",
            "batch_size": 25,
            "dry_run": True,
            "source_token": "tok",
            "verify_tls": False,
            "source_username": "admin",
            "source_password": "pw",
            "field_mapping": {"title": "field_headline"},
        },
    )
    assert service.calls[1] == (
        "reconcile_counts",
        {"migration_id": "d7_upgrade", "target_resource_types": ["node--article", "user--user"]},
    )


def test_run_migration_passes_continue_on_error_through(monkeypatch, tmp_path) -> None:
    service = _PlanService()
    fns = _migration_fns(monkeypatch, tmp_path, migration_service=service)

    asyncio.run(
        fns["run_migration"](
            "d7_upgrade",
            entity_types=["node", "user"],
            dry_run=True,
            source_token="tok",
            verify_tls=False,
            source_username="admin",
            source_password="pw",
            continue_on_error=True,
        )
    )

    assert service.calls == [
        (
            "run_migration",
            {
                "migration_id": "d7_upgrade",
                "entity_types": ["node", "user"],
                "dry_run": True,
                "source_token": "tok",
                "verify_tls": False,
                "source_username": "admin",
                "source_password": "pw",
                "continue_on_error": True,
            },
        )
    ]


def test_plan_wrappers_answer_honestly_when_the_service_is_gone() -> None:
    """Every plan tool guards a missing service with one answer per
    shape — an error dict, and a list-of-error for the list tool."""
    fns = _register("migration", migration_service=False)

    assert asyncio.run(fns["create_migration_plan"]("x")) == {
        "error": "Migration service not available"
    }
    assert asyncio.run(fns["get_migration_plan"]("x")) == {
        "error": "Migration service not available"
    }
    assert asyncio.run(fns["list_migration_plans"]()) == [
        {"error": "Migration service not available"}
    ]
    assert asyncio.run(fns["migration_status"]("x")) == {
        "error": "Migration service not available"
    }
    assert asyncio.run(fns["run_migration"]("x")) == {
        "error": "Migration service not available"
    }
