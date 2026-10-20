"""Offline tests for the module-development scaffold writers.

Until now no test in this repository touched any of the twelve
``module_dev`` tools (or the test scaffolds): their only judge was the
weekly live sweep, which proves a tool *answers* — not that the files
it writes are files Drupal or PHP can actually use. A sweep that counts
verdicts cannot see the artefacts, and writing this first batch caught
four defects that had shipped in every release:

- ``module_create`` reported two of its ``files_created`` paths wrong
  (a missing ``f`` on the controller, the schema file listed at module
  root though it is written under ``config/schema/``), so a caller
  following its own report never found the files;
- ``module_service_create`` pasted ``$this->x = $x;`` at class scope —
  a PHP ParseError whenever ``arguments`` were passed — and kept dots
  from service ids in PHP variable names (``$entity_type.manager``);
- ``test_scaffold_phpunit`` wrote a shell-style ``\\$this`` into raw
  PHP that no shell ever processes, the same shape as ``queue_create``'s
  ``\\$`` bug the sweep already exposed;
- ``module_test_create`` wrote those same shell escapes (three per
  file) *and* a pluralized namespace — ``...\\KernelTests`` — matching
  none of the directories it puts the files in, so Drupal's PSR-4 test
  discovery never loads a class it scaffolds.

Each test pins the shape that was wrong, so none can return silently.
"""

import asyncio
from typing import Any

import yaml

from tests.unit.test_tool_utils import _Drush, _register


def _writer(module_name: str, **deps: Any) -> dict[str, Any]:
    """Register a tools module with a drush client that is merely present.

    These writers only *check* that drush exists; they never call it, so
    a recording client is enough to exercise the file paths.
    """
    deps.setdefault("drush_client", _Drush({"returncode": 0, "data": {}}))
    return _register(module_name, **deps)


# --- module_create --------------------------------------------------------


def test_module_create_refuses_to_run_without_drush() -> None:
    """The documented guard must fire before any file is touched."""
    fns = _register("module_dev", drush_client=None)

    result = asyncio.run(fns["module_create"]("Thing"))

    assert result == {"error": "Drush not available"}


def test_module_create_rejects_a_machine_name_php_cannot_use() -> None:
    """`9lives` is not a PHP identifier, and the default derivation
    (name.lower().replace(" ", "_")) produces such names from ordinary
    titles like "9lives". Writing the module anyway would emit files
    Drupal can never discover."""
    fns = _writer("module_dev")

    result = asyncio.run(fns["module_create"]("Nine", machine_name="9lives"))

    assert "Invalid machine name" in result["error"]
    assert "9lives" in result["error"]


def test_module_create_writes_a_module_drupal_can_read(tmp_path) -> None:
    """The full default scaffold, asserted field by field."""
    fns = _writer("module_dev")
    module = tmp_path / "my_module"

    result = asyncio.run(
        fns["module_create"](
            "My Module",
            description="Does things",
            dependencies=["drupal:node"],
            path=str(module),
        )
    )

    assert result["success"] is True
    assert result["machine_name"] == "my_module"

    info = yaml.safe_load((module / "my_module.info.yml").read_text())
    assert info["type"] == "module"
    assert info["dependencies"] == ["drupal:node"]
    assert "^10" in info["core_version_requirement"]

    routing = yaml.safe_load((module / "my_module.routing.yml").read_text())
    entry = routing["my_module.content"]
    assert entry["defaults"]["_controller"].startswith("\\Drupal\\my_module\\Controller\\")
    # The route must be gated on the permission the scaffold also writes.
    assert entry["requirements"]["_permission"] == "administer my_module"

    perms = yaml.safe_load((module / "my_module.permissions.yml").read_text())
    assert "administer my_module" in perms

    services = yaml.safe_load((module / "my_module.services.yml").read_text())
    assert services["services"]["my_module.example_service"]["class"] == (
        "Drupal\\my_module\\Service\\ExampleService"
    )

    module_php = (module / "my_module.module").read_text()
    assert "function my_module_help" in module_php
    assert "function my_module_permissions" in module_php

    # The schema lives under config/schema/, typed, for the settings it declares.
    schema = yaml.safe_load((module / "config" / "schema" / "my_module.schema.yml").read_text())
    assert schema["my_module.settings"]["type"] == "config_object"
    assert schema["my_module.settings"]["mapping"]["enabled"]["type"] == "boolean"


def test_module_create_reports_only_files_it_actually_wrote(tmp_path) -> None:
    """Every non-null `files_created` entry must resolve on disk.

    Two entries did not: the controller path was a plain string with a
    literal `{machine_name.capitalize()}` in it (no `f` prefix), and the
    schema file was listed at module root though the tool writes it to
    `config/schema/`. A caller walking the report hit nothing both times.
    """
    fns = _writer("module_dev")
    module = tmp_path / "my_module"

    result = asyncio.run(fns["module_create"]("My Module", path=str(module)))

    reported = [entry for entry in result["files_created"] if entry]
    assert reported, "the scaffold reported no files at all"
    missing = [entry for entry in reported if not (module / entry).exists()]
    assert missing == [], f"reported files that were never written: {missing}"
    # Pin the two that were wrong outright.
    assert "src/Controller/My_moduleController.php" in reported
    assert "config/schema/my_module.schema.yml" in reported


def test_module_create_honours_the_switches_it_offers(tmp_path) -> None:
    """`generate_*=False` must suppress the file *and* its report entry."""
    fns = _writer("module_dev")
    module = tmp_path / "lean"

    result = asyncio.run(
        fns["module_create"](
            "Lean",
            machine_name="lean",
            generate_routing=False,
            generate_services=False,
            generate_permissions=False,
            generate_config_schema=False,
            path=str(module),
        )
    )

    assert not (module / "lean.routing.yml").exists()
    assert not (module / "lean.services.yml").exists()
    assert not (module / "lean.permissions.yml").exists()
    assert not (module / "config").exists()
    # The two unconditional files are still there.
    assert (module / "lean.info.yml").exists()
    assert (module / "lean.module").exists()
    reported = [entry for entry in result["files_created"] if entry]
    assert reported == ["lean.info.yml", "lean.module"]


# --- module_service_create ------------------------------------------------


def test_module_service_create_reports_a_missing_module(tmp_path) -> None:
    """Writing services.yml beside nothing would create a directory tree
    Drupal has no module to load from."""
    fns = _writer("module_dev")

    result = asyncio.run(
        fns["module_service_create"]("ghost", "cache", path=str(tmp_path / "ghost"))
    )

    assert "Module not found" in result["error"]
    assert str(tmp_path / "ghost") in result["error"]


def test_module_service_create_wires_arguments_into_valid_php(tmp_path) -> None:
    """Arguments must become constructor params and properties, nowhere else.

    This pins two shipped defects at once: the constructor body was also
    pasted at class scope (statements in a class body are a ParseError
    whenever `arguments` were passed), and dots from service ids leaked
    into PHP variable names — `@entity_type.manager` became the illegal
    `$entity_type.manager`.
    """
    fns = _writer("module_dev")
    module = tmp_path / "m"
    module.mkdir()

    result = asyncio.run(
        fns["module_service_create"](
            "m",
            "cache",
            arguments=["@entity_type.manager", "@renderer"],
            tags=[{"name": "event_subscriber"}],
            path=str(module),
        )
    )

    assert result["success"] is True
    services = yaml.safe_load((module / "m.services.yml").read_text())
    definition = services["services"]["m.cache"]
    assert definition["class"] == "Drupal\\m\\Service\\MCacheService"
    assert definition["arguments"] == ["@entity_type.manager", "@renderer"]
    assert definition["tags"] == [{"name": "event_subscriber"}]

    php = (module / "src" / "Service" / "MCacheService.php").read_text()
    # Dots never survive into variable names.
    assert "$entity_type.manager" not in php
    assert "public function __construct($entity_type_manager, $renderer)" in php
    assert "$this->entity_type_manager = $entity_type_manager;" in php
    # Property declarations, not assignments, may sit at class scope.
    class_scope = php.split("public function __construct")[0]
    assert "$this->" not in class_scope
    assert "protected $entity_type_manager;" in class_scope


def test_module_service_create_preserves_existing_definitions(tmp_path) -> None:
    """services.yml is read, extended and rewritten — never truncated."""
    fns = _writer("module_dev")
    module = tmp_path / "m"
    module.mkdir()
    (module / "m.services.yml").write_text(
        "services:\n  m.legacy:\n    class: Drupal\\m\\Legacy\n"
    )

    asyncio.run(fns["module_service_create"]("m", "cache", path=str(module)))

    services = yaml.safe_load((module / "m.services.yml").read_text())
    assert set(services["services"]) == {"m.legacy", "m.cache"}


# --- test_scaffold_phpunit ------------------------------------------------


def test_phpunit_scaffold_writes_php_a_php_parser_accepts(tmp_path, monkeypatch) -> None:
    """No shell touches this file, so no shell escapes may appear in it.

    The scaffold wrote `\\$this->assertTrue(TRUE);` — a backslash the
    PHP parser rejects outright — for every generated test method. The
    path is relative to the working directory, so the test owns cwd.
    """
    monkeypatch.chdir(tmp_path)
    fns = _writer("testing")

    result = asyncio.run(
        fns["test_scaffold_phpunit"]("mymodule", test_methods=["saves", "loads"])
    )

    created = tmp_path / "mymodule" / "tests" / "src" / "Unit" / "MymoduleTest.php"
    assert result["created"] == "mymodule/tests/src/Unit/MymoduleTest.php"
    assert created.is_file()
    php = created.read_text()

    assert r"\$this" not in php, "a shell escape leaked into raw PHP"
    assert "$this->assertTrue(TRUE);" in php
    assert "public function testSaves()" in php
    assert "public function testLoads()" in php
    assert "namespace Drupal\\Tests\\mymodule\\Unit;" in php
    assert "extends Drupal\\Tests\\UnitTestCase" in php


def test_phpunit_scaffold_kernel_type_uses_the_kernel_base(tmp_path, monkeypatch) -> None:
    """`test_type` picks both the directory and the base class; only the
    unit default had ever been exercised."""
    monkeypatch.chdir(tmp_path)
    fns = _writer("testing")

    asyncio.run(fns["test_scaffold_phpunit"]("mymodule", test_type="kernel"))

    created = tmp_path / "mymodule" / "tests" / "src" / "Kernel" / "MymoduleTest.php"
    php = created.read_text()
    assert "extends Drupal\\KernelTests\\KernelTestBase" in php
    assert "namespace Drupal\\Tests\\mymodule\\Kernel;" in php


# --- module_test_create ---------------------------------------------------


def test_module_test_create_writes_a_discoverable_test(tmp_path) -> None:
    """The kernel skeleton was wrong twice over, and both faults are silent.

    Shell escapes went into raw PHP (`protected static \\$modules`,
    `\\$this->...`) — the parser rejects them, so the file it wrote was
    never runnable. And the namespace was pluralized (`KernelTests`,
    `UnitTests`, `FunctionalTests`) while the file lands in
    `tests/src/Kernel` & friends, so PSR-4 discovery never loads it: a
    scaffolded test that PHPUnit cannot find never runs, and nothing
    reports an error.
    """
    fns = _writer("module_dev")
    module = tmp_path / "m"
    module.mkdir()

    result = asyncio.run(
        fns["module_test_create"](
            "m",
            "smoke",
            test_type="KernelTest",
            test_methods=["creation"],
            path=str(module),
        )
    )

    test_file = module / "tests" / "src" / "Kernel" / "MSmokeTest.php"
    assert result["test_file"] == str(test_file)
    php = test_file.read_text()

    assert r"\$" not in php, "a shell escape leaked into raw PHP"
    assert "protected static $modules = ['m'];" in php
    assert "$this->assertTrue(TRUE);" in php
    # The namespace must be the directory the file sits in, un-pluralized.
    # (`Drupal\KernelTests\KernelTestBase` — the import — may keep it.)
    assert "namespace Drupal\\Tests\\m\\Kernel;" in php
    assert "namespace Drupal\\Tests\\m\\KernelTests;" not in php
    assert "extends KernelTestBase" in php
    assert "@group m" in php
    assert "public function testCreation()" in php


def test_module_test_create_rejects_an_unknown_test_type(tmp_path) -> None:
    """The available types are part of the answer, not an empty refusal."""
    fns = _writer("module_dev")
    module = tmp_path / "m"
    module.mkdir()

    result = asyncio.run(
        fns["module_test_create"]("m", "smoke", test_type="SweepTest", path=str(module))
    )

    assert "Unknown test type" in result["error"]
    assert "KernelTest, UnitTest, FunctionalTest" in result["error"]
