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

Each test pins the shape that was wrong, so none can return silently.
"""

import asyncio
from typing import Any

import yaml

from tests.unit.test_tool_utils import _Drush, _register


def _writer(module_name: str, **deps: Any) -> dict[str, Any]:
    """Register a tools module with a drush client that is merely present."""
    deps.setdefault("drush_client", _Drush({"returncode": 0, "data": {}}))
    return _register(module_name, **deps)


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
