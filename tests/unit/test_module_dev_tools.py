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

The second pass covered the remaining writers and found the same
disease one layer down:

- ``module_plugin_create`` never closed the plugin docblock, so the
  class declaration sat inside a comment on every call; formatters got
  the widget's ``formElement`` instead of the abstract ``viewElements``
  (a fatal on load); and the widget/views signatures named
  ``FormStateInterface``/``ResultRow`` without importing them;
- ``module_form_create``, ``module_controller_create`` and
  ``module_event_subscriber_create`` reported file paths relative to
  the module they were never rooted at, and ``EntityForm`` was
  scaffolded as a FormBase;
- ``module_event_subscriber_create`` subscribed methods it never
  generated — a fatal the first time a non-default event fires;
- ``module_hook_implement`` offered ``hook_config_import_create``, a
  hook Drupal has never invoked;
- ``module_info_generate`` and ``module_dependencies_analyze``
  "detected dependencies" that are not modules at all ("form",
  "entity", "container"), producing info.yml files no site can install
  and suggestions no developer can use.

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


# --- module_plugin_create -------------------------------------------------


def test_module_plugin_create_reports_a_missing_module(tmp_path) -> None:
    """No module directory, no plugin: the guard fires first."""
    fns = _writer("module_dev")

    result = asyncio.run(
        fns["module_plugin_create"](
            "ghost", "block", "ghost_block", "Ghost", path=str(tmp_path / "ghost")
        )
    )

    assert "Module not found" in result["error"]


def test_module_plugin_create_names_the_types_it_can_scaffold(tmp_path) -> None:
    """An unknown type must answer with the list, not a bare refusal."""
    fns = _writer("module_dev")
    module = tmp_path / "m"
    module.mkdir()

    result = asyncio.run(
        fns["module_plugin_create"]("m", "sweep", "x", "X", path=str(module))
    )

    assert "Unknown plugin type" in result["error"]
    assert "block" in result["error"]
    assert "field_formatter" in result["error"]


def test_module_plugin_create_closes_the_plugin_docblock(tmp_path) -> None:
    """The annotation docblock must terminate before the class opens.

    It never did — the template ended at the annotation's ``)`` with no
    ``*/``, so on every call the ``class`` line landed *inside* the
    comment and the file was an unterminated block comment: a parse
    error the moment anything read it.
    """
    fns = _writer("module_dev")
    module = tmp_path / "m"
    module.mkdir()

    result = asyncio.run(
        fns["module_plugin_create"](
            "m", "block", "hello_block", "Hello block", path=str(module)
        )
    )

    assert result["success"] is True
    plugin_file = module / "src" / "Plugin" / "Block" / f"{result['class_name']}.php"
    assert plugin_file.is_file()
    assert result["plugin_file"] == str(plugin_file)
    php = plugin_file.read_text()

    docblock, sep, rest = php.partition(f"class {result['class_name']}")
    assert sep, "the class declaration is missing"
    assert " */" in docblock, "the plugin docblock is never closed"
    # PSR-4: the namespace matches the directory the file lands in.
    assert "namespace Drupal\\m\\Plugin\\Block;" in php
    assert 'id = "hello_block",' in php
    assert 'admin_label = @Translation("Hello block"),' in php


def test_module_plugin_create_widget_imports_the_types_it_typehints(tmp_path) -> None:
    """`formElement` type-hints FormStateInterface; without the import it
    resolves into the plugin's own namespace, so the first call fatals."""
    fns = _writer("module_dev")
    module = tmp_path / "m"
    module.mkdir()

    result = asyncio.run(
        fns["module_plugin_create"](
            "m", "field_widget", "m_widget", "Widget", path=str(module)
        )
    )

    php = (module / "src" / "Plugin" / "Field" / "FieldWidget" / f"{result['class_name']}.php").read_text()
    assert "use Drupal\\Core\\Form\\FormStateInterface;" in php
    assert "public function formElement(" in php
    assert "FormStateInterface $form_state" in php
    # A widget implements formElement, not the formatter's method.
    assert "viewElements" not in php


def test_module_plugin_create_formatter_implements_the_abstract_method(
    tmp_path,
) -> None:
    """FormatterBase's abstract method is viewElements; the scaffold gave
    formatters the widget's formElement instead — a fatal ("class
    contains 1 abstract method") the moment Drupal instantiates it."""
    fns = _writer("module_dev")
    module = tmp_path / "m"
    module.mkdir()

    result = asyncio.run(
        fns["module_plugin_create"](
            "m", "field_formatter", "m_fmt", "Formatter", path=str(module)
        )
    )

    php = (
        module / "src" / "Plugin" / "Field" / "FieldFormatter"
        / f"{result['class_name']}.php"
    ).read_text()
    assert "public function viewElements(FieldableEntityInterface $entity, $langcode)" in php
    assert "use Drupal\\Core\\Entity\\FieldableEntityInterface;" in php
    # formElement belongs to widgets; a formatter must not declare it.
    assert "formElement" not in php


def test_module_plugin_create_views_field_imports_result_row(tmp_path) -> None:
    r"""`render(ResultRow $values)` without `use Drupal\views\ResultRow`
    type-hints a class that does not exist in that namespace."""
    fns = _writer("module_dev")
    module = tmp_path / "m"
    module.mkdir()

    result = asyncio.run(
        fns["module_plugin_create"](
            "m", "views_field", "m_field", "Field", path=str(module)
        )
    )

    php = (module / "src" / "Plugin" / "views" / "field" / f"{result['class_name']}.php").read_text()
    assert "use Drupal\\views\\ResultRow;" in php
    assert "public function render(ResultRow $values)" in php


# --- module_form_create ---------------------------------------------------


def test_module_form_create_config_form_wires_config_end_to_end(tmp_path) -> None:
    """The ConfigForm scaffold: container creation, config names, field
    round-trip into config, route and service registration — and a
    reported form_file that actually resolves."""
    fns = _writer("module_dev")
    module = tmp_path / "m"
    module.mkdir()

    result = asyncio.run(
        fns["module_form_create"](
            "m",
            "settings_page",
            fields=[{"name": "site_label", "type": "textfield", "title": "Site label"}],
            path=str(module),
        )
    )

    assert result["success"] is True
    cls = result["class_name"]
    form_file = module / "src" / "Form" / f"{cls}.php"
    assert form_file.is_file()
    # The report used to be a bare "src/Form/X.php" with no module root.
    assert result["form_file"] == str(form_file)
    php = form_file.read_text()

    assert "use Drupal\\Core\\Config\\ConfigFactoryInterface;" in php
    assert "public static function create(ContainerInterface $container)" in php
    assert "protected function getEditableConfigNames()" in php
    assert "$config->set('site_label', $form_state->getValue('site_label'));" in php

    routing = yaml.safe_load((module / "m.routing.yml").read_text())
    entry = routing["m.settings_page"]
    assert entry["defaults"]["_form"] == f"\\Drupal\\m\\Form\\{cls}"
    assert entry["requirements"]["_permission"] == "administer m"

    services = yaml.safe_load((module / "m.services.yml").read_text())
    assert services["services"]["m.form.settings_page"]["arguments"] == ["@config.factory"]


def test_module_form_create_refuses_to_fake_an_entity_form(tmp_path) -> None:
    """EntityForm used to fall into the FormBase branch: the class
    extended EntityForm while implementing none of its contract, and
    the tool has no entity type to route it with (entity forms are
    routed with _entity_form, not _form). An honest refusal beats a
    class that cannot load."""
    fns = _writer("module_dev")
    module = tmp_path / "m"
    module.mkdir()

    result = asyncio.run(
        fns["module_form_create"]("m", "node_form", form_type="EntityForm", path=str(module))
    )

    assert "EntityForm" in result["error"]
    assert "_entity_form" in result["error"]
    # Nothing half-written on the way out.
    assert not (module / "src").exists()


def test_module_form_create_names_the_types_it_can_scaffold(tmp_path) -> None:
    fns = _writer("module_dev")
    module = tmp_path / "m"
    module.mkdir()

    result = asyncio.run(
        fns["module_form_create"]("m", "x", form_type="SweepForm", path=str(module))
    )

    assert "Unknown form type" in result["error"]
    assert "ConfigForm" in result["error"]


# --- module_controller_create ---------------------------------------------


def test_module_controller_create_writes_methods_routes_and_a_real_path(
    tmp_path,
) -> None:
    """One method per entry, routes pointing at ClassName::method, and a
    controller_file report that resolves (it used to be a bare
    src/Controller/... with no module root)."""
    fns = _writer("module_dev")
    module = tmp_path / "m"
    module.mkdir()

    result = asyncio.run(
        fns["module_controller_create"](
            "m",
            "dashboard",
            methods=[
                {"name": "content", "route": "/m/dashboard", "title": "Dashboard"},
                {"name": "export", "route": "/m/dashboard/export"},
            ],
            path=str(module),
        )
    )

    assert result["success"] is True
    cls = result["class_name"]
    controller_file = module / "src" / "Controller" / f"{cls}.php"
    assert controller_file.is_file()
    assert result["controller_file"] == str(controller_file)
    php = controller_file.read_text()
    assert "public function content()" in php
    assert "public function export()" in php

    routing = yaml.safe_load((module / "m.routing.yml").read_text())
    assert routing["m.content"]["defaults"]["_controller"] == (
        f"\\Drupal\\m\\Controller\\{cls}::content"
    )
    assert routing["m.export"]["path"] == "/m/dashboard/export"


# --- module_event_subscriber_create ---------------------------------------


def test_module_event_subscriber_create_registers_the_service(tmp_path) -> None:
    """Default events: both handlers present, service tagged, reported
    subscriber_file resolving to the file on disk."""
    fns = _writer("module_dev")
    module = tmp_path / "m"
    module.mkdir()

    result = asyncio.run(
        fns["module_event_subscriber_create"]("m", "logger", path=str(module))
    )

    assert result["success"] is True
    cls = result["class_name"]
    subscriber_file = module / "src" / "EventSubscriber" / f"{cls}.php"
    assert subscriber_file.is_file()
    assert result["subscriber_file"] == str(subscriber_file)
    php = subscriber_file.read_text()
    assert '"kernel.request" => [["onKernelRequest", 0]],' in php
    assert "public function onKernelRequest(RequestEvent $event)" in php
    assert "public function onKernelResponse(ResponseEvent $event)" in php

    services = yaml.safe_load((module / "m.services.yml").read_text())
    definition = services["services"][result["service_id"]]
    assert definition["class"] == f"Drupal\\m\\EventSubscriber\\{cls}"
    assert definition["tags"] == [{"name": "event_subscriber"}]


def test_module_event_subscriber_create_generates_the_methods_it_subscribes(
    tmp_path,
) -> None:
    """getSubscribedEvents used to advertise whatever the caller asked
    for while the class only ever defined the two kernel handlers — the
    first time a custom event fired, Drupal called a method that did
    not exist. Every subscribed method must be generated."""
    fns = _writer("module_dev")
    module = tmp_path / "m"
    module.mkdir()

    result = asyncio.run(
        fns["module_event_subscriber_create"](
            "m",
            "terminator",
            events=[
                {"event": "kernel.terminate", "method": "onKernelTerminate", "priority": 100},
            ],
            path=str(module),
        )
    )

    php = (
        module / "src" / "EventSubscriber" / f"{result['class_name']}.php"
    ).read_text()
    assert '"kernel.terminate" => [["onKernelTerminate", 100]],' in php
    assert "public function onKernelTerminate(Event $event)" in php
    assert "use Symfony\\Contracts\\EventDispatcher\\Event;" in php
    # Only what was requested: the default kernel handlers are gone.
    assert "onKernelRequest" not in php
    assert "onKernelResponse" not in php


# --- module_hook_implement ------------------------------------------------


def test_module_hook_implement_appends_once_and_refuses_duplicates(tmp_path) -> None:
    fns = _writer("module_dev")
    module = tmp_path / "m"
    module.mkdir()
    module_file = module / "m.module"
    module_file.write_text("<?php\n")

    result = asyncio.run(fns["module_hook_implement"]("m", "hook_cron", path=str(module)))

    assert result["success"] is True
    content = module_file.read_text()
    assert "function m_cron()" in content
    assert "Implements hook_cron()." in content

    again = asyncio.run(fns["module_hook_implement"]("m", "hook_cron", path=str(module)))
    assert "already implemented" in again["error"]


def test_module_hook_implement_offers_only_hooks_drupal_invokes(tmp_path) -> None:
    """The catalog used to include hook_config_import_create — a hook
    that exists in no Drupal version. A function named for it is code
    that never runs; the real config hook is hook_config_presave."""
    fns = _writer("module_dev")
    module = tmp_path / "m"
    module.mkdir()
    (module / "m.module").write_text("<?php\n")

    invented = asyncio.run(
        fns["module_hook_implement"]("m", "hook_config_import_create", path=str(module))
    )
    assert "Unknown hook" in invented["error"]

    real = asyncio.run(
        fns["module_hook_implement"]("m", "hook_config_presave", path=str(module))
    )
    assert real["success"] is True
    content = (module / "m.module").read_text()
    assert "function m_config_presave(" in content

    unknown = asyncio.run(fns["module_hook_implement"]("m", "hook_nope", path=str(module)))
    assert "Unknown hook" in unknown["error"]
    assert "hook_help" in unknown["error"]


# --- module_info_generate -------------------------------------------------


def test_module_info_generate_infers_dependencies_from_class_usage(tmp_path) -> None:
    """Dependencies must be module names a site can install.

    The old detection looked for the literal text "hook_form_alter" and
    mapped hits to words like "form" and "entity" — not modules — so the
    generated info.yml declared dependencies Drupal refuses to install.
    Class usage (\\Drupal\\webform\\...) is the reliable signal.
    """
    fns = _writer("module_dev")
    module = tmp_path / "m"
    module.mkdir()
    (module / "m.module").write_text(
        "<?php\n"
        "use Drupal\\webform\\WebformSubmissionInterface;\n"
        "function m_form_alter(array &$form, FormStateInterface $form_state, $form_id) {}\n"
    )

    result = asyncio.run(fns["module_info_generate"]("m", path=str(module)))

    assert result["success"] is True
    assert result["info_file"] == str(module / "m.info.yml")
    info = yaml.safe_load((module / "m.info.yml").read_text())
    assert info["type"] == "module"
    assert info["dependencies"] == ["webform"]
    # Hook words are not modules and must never reappear as dependencies.
    assert "form" not in info.get("dependencies", [])


def test_module_info_generate_writes_no_dependencies_without_usage(tmp_path) -> None:
    """A module using only core APIs depends on nothing; the old check
    still produced ["cron"] from a cron hook implementation."""
    fns = _writer("module_dev")
    module = tmp_path / "m"
    module.mkdir()
    (module / "m.module").write_text("<?php\nfunction m_cron() {}\n")

    asyncio.run(fns["module_info_generate"]("m", path=str(module)))

    info = yaml.safe_load((module / "m.info.yml").read_text())
    assert "dependencies" not in info


# --- module_permission_create / module_config_schema_create ---------------


def test_module_permission_create_defaults_then_merges(tmp_path) -> None:
    fns = _writer("module_dev")
    module = tmp_path / "m"
    module.mkdir()

    first = asyncio.run(fns["module_permission_create"]("m", path=str(module)))

    assert first["success"] is True
    assert first["permissions_file"] == str(module / "m.permissions.yml")
    perms = yaml.safe_load((module / "m.permissions.yml").read_text())
    assert set(perms) == {"administer m", "access m content"}

    asyncio.run(
        fns["module_permission_create"](
            "m", permissions=[{"id": "flip switches", "title": "Flip"}], path=str(module)
        )
    )

    perms = yaml.safe_load((module / "m.permissions.yml").read_text())
    assert set(perms) == {"administer m", "access m content", "flip switches"}
    assert perms["flip switches"]["title"] == "Flip"


def test_module_config_schema_create_defaults_then_merges(tmp_path) -> None:
    fns = _writer("module_dev")
    module = tmp_path / "m"
    module.mkdir()

    first = asyncio.run(fns["module_config_schema_create"]("m", path=str(module)))

    assert first["success"] is True
    schema_file = module / "config" / "schema" / "m.schema.yml"
    assert first["schema_file"] == str(schema_file)
    data = yaml.safe_load(schema_file.read_text())
    assert data["m.settings"]["type"] == "config_object"
    assert data["m.settings"]["mapping"]["enabled"]["type"] == "boolean"

    asyncio.run(
        fns["module_config_schema_create"](
            "m", schema_name="m.other", schema={"m.other": {"type": "config_object"}},
            path=str(module),
        )
    )

    data = yaml.safe_load(schema_file.read_text())
    assert set(data) == {"m.settings", "m.other"}


# --- module_dependencies_analyze ------------------------------------------


def test_module_dependencies_analyze_suggests_real_modules_only(tmp_path) -> None:
    """Class usage implies module dependencies; hook words and core
    plumbing do not.

    The old scanner searched for `\\(Foo::class\\)` — a pattern nothing
    in real PHP looks like — and its hook map turned any form_alter
    into a dependency on a module named "form", ContainerInterface
    into "container". Neither exists. A declared "drupal:webform" also
    already satisfies a "webform" suggestion.
    """
    fns = _writer("module_dev")
    module = tmp_path / "m"
    module.mkdir()
    (module / "m.module").write_text(
        "<?php\n"
        "use Drupal\\webform\\WebformSubmissionInterface;\n"
        "use Drupal\\views\\Views;\n"
        "use Drupal\\Core\\Form\\FormStateInterface;\n"
        "use Symfony\\Component\\DependencyInjection\\ContainerInterface;\n"
        "function m_form_alter(array &$form, FormStateInterface $form_state, $form_id) {\n"
        "  Views::getView('latest_content');\n"
        "}\n"
    )
    (module / "m.info.yml").write_text("dependencies:\n  - drupal:webform\n")

    result = asyncio.run(fns["module_dependencies_analyze"]("m", path=str(module)))

    assert result["success"] is True
    assert result["existing_dependencies"] == ["drupal:webform"]
    # Core and Symfony namespaces are not modules; neither are hook words.
    assert result["all_detected"] == ["views", "webform"]
    assert result["suggested_dependencies"] == ["views"]


def test_module_dependencies_analyze_reports_a_missing_module(tmp_path) -> None:
    fns = _writer("module_dev")

    result = asyncio.run(
        fns["module_dependencies_analyze"]("ghost", path=str(tmp_path / "ghost"))
    )

    assert "Module not found" in result["error"]
