"""Tests for the shared tool helpers and for the DevOps setup tools."""

from pathlib import Path
from typing import Any

from drupal_mcp_server.tools._utils import b64_text, drush_output, drush_result, ensure_dict


def test_drush_result_reports_stderr_when_a_command_fails():
    """Ten tools returned a bare exit code, hiding why the command failed."""
    payload = drush_result({
        "returncode": 255,
        "data": {},
        "stderr": 'Error: unknown command "feeds:import"',
        "command": "drush feeds:import",
    })

    assert payload["returncode"] == 255
    assert "unknown command" in payload["error"]
    assert payload["command"] == "drush feeds:import"


def test_drush_result_omits_error_on_success():
    payload = drush_result({"returncode": 0, "data": {"ok": True}, "stderr": ""})

    assert "error" not in payload
    assert payload["returncode"] == 0


def test_ensure_dict_surfaces_a_failed_drush_command():
    """224 call sites pipe Drush straight through ``ensure_dict``.

    A failed run arrives as ``{returncode: 1, data: {}, stderr: ...}`` with no
    ``error`` key - byte for byte what an empty successful result looks like -
    so an MCP client reading ``data`` saw a broken command as "no rows", and
    the live sweep counted those tools as passing.
    """
    payload = ensure_dict({
        "returncode": 1,
        "data": {},
        "stderr": '  Too many arguments to "sql:query" command  ',
        "command": "ddev drush sql:query SHOW TABLES",
    })

    assert "Too many arguments" in payload["error"]
    # Everything else survives: this adds a key rather than replacing the shape.
    assert payload["returncode"] == 1
    assert payload["data"] == {}
    assert payload["command"] == "ddev drush sql:query SHOW TABLES"


def test_ensure_dict_is_silent_when_the_command_succeeded():
    # A drush run that worked.
    assert "error" not in ensure_dict({"returncode": 0, "data": {"rows": [1]}})
    # JSON:API payloads carry no returncode at all and must be untouched.
    assert ensure_dict({"data": [{"id": "1"}]}) == {"data": [{"id": "1"}]}
    assert ensure_dict(None) == {"error": "No response"}
    assert ensure_dict([1, 2]) == {"data": [1, 2]}


def test_b64_text_survives_a_php_string_intact():
    """PHP has no `\\uXXXX` escape, so non-ASCII text must not be interpolated.

    `Ünïcode "quoted" $var \\path` is exactly the string that either breaks the
    statement or mangles silently when dropped into PHP source; base64 makes it
    inert to PHP, the shell and Drush alike.
    """
    import base64
    import json

    original = 'Ünïcode "quoted" $var \\path'
    encoded = b64_text(original)

    # It is plain ASCII, so nothing along the way can reinterpret it.
    assert encoded.isascii()
    assert "\"" not in encoded and "$" not in encoded and "\\" not in encoded
    # And PHP's base64_decode() - reproduced here - returns it byte for byte.
    assert base64.b64decode(encoded).decode("utf-8") == original

    # Structured values are stringified rather than JSON-encoded, which is what
    # the PHP side expects from base64_decode() alone.
    assert base64.b64decode(b64_text(json.dumps({"a": 1}))).decode() == '{"a": 1}'


def test_drush_result_keeps_extra_fields():
    payload = drush_result({"returncode": 0, "data": {}}, path="/tmp", role="authenticated")

    assert payload["path"] == "/tmp"
    assert payload["role"] == "authenticated"


def test_drush_result_reports_a_missing_error_message():
    payload = drush_result({"returncode": 1, "data": {}, "stderr": ""})

    assert payload["error"] == "drush failed: no error output"


def test_drush_output_reads_parsed_data_not_a_missing_stdout_key():
    """DrushClient has no `stdout` key; reading one always gave None."""
    assert drush_output({"data": {"output": "plain text"}}) == "plain text"
    assert drush_output({"data": {"a": 1}}) == '{\n  "a": 1\n}'
    assert drush_output({"data": "already text"}) == "already text"
    assert drush_output({"data": {}}) == ""


def _register_devops(tmp_path: Path) -> dict[str, Any]:
    from drupal_mcp_server.tools import devops

    class FakeMCP:
        def __init__(self) -> None:
            self.fns: dict[str, Any] = {}

        def tool(self, *args: Any, **kwargs: Any):
            def decorate(fn):
                self.fns[fn.__name__] = fn
                return fn

            return decorate

    mcp = FakeMCP()
    devops.register_tools(mcp, site_manager=object(), drush_client=None)  # type: ignore[arg-type]
    return mcp.fns


def test_ddev_setup_refuses_to_overwrite_an_existing_config(tmp_path: Path):
    """Calling it with defaults used to replace a working config with
    `name: .`, which takes the DDEV project down."""
    config = tmp_path / ".ddev" / "config.yaml"
    config.parent.mkdir()
    config.write_text("name: my-project\ntype: drupal10\nwebroot: web\n")

    import asyncio

    result = asyncio.run(_register_devops(tmp_path)["ddev_setup"](str(tmp_path)))

    assert "already exists" in result["error"]
    assert "force=True" in result["error"]
    assert config.read_text().startswith("name: my-project")


def test_ddev_setup_writes_a_config_ddev_accepts(tmp_path: Path):
    """DDEV 1.24 accepts `type:` not `kind:`, and reads `docroot:` - an
    unrecognised key is dropped silently, which leaves an empty docroot and
    makes nginx serve the project root instead of Drupal."""
    import asyncio

    project = tmp_path / "my-site"
    result = asyncio.run(_register_devops(tmp_path)["ddev_setup"](str(project)))

    assert result["status"] == "created"
    written = (project / ".ddev" / "config.yaml").read_text()
    assert written == "name: my-site\ntype: drupal10\ndocroot: web\n"
    assert "webroot" not in written
    assert "kind" not in written


def test_ddev_setup_rejects_a_name_that_is_not_a_hostname(tmp_path: Path):
    import asyncio

    project = tmp_path / "My Site!"
    result = asyncio.run(_register_devops(tmp_path)["ddev_setup"](str(project)))

    assert "not a usable DDEV project name" in result["error"]
    assert not (project / ".ddev").exists()


def test_lando_setup_also_refuses_to_overwrite(tmp_path: Path):
    import asyncio

    config = tmp_path / ".lando.yml"
    config.write_text("name: hand-tuned\nrecipe: drupal10\n")

    result = asyncio.run(_register_devops(tmp_path)["lando_setup"](str(tmp_path)))

    assert "already exists" in result["error"]
    assert config.read_text().startswith("name: hand-tuned")


# --- Drush command names the sweep proved wrong ---------------------------


def _register(module_name: str, **deps: Any) -> dict[str, Any]:
    import importlib

    module = importlib.import_module(f"drupal_mcp_server.tools.{module_name}")

    class FakeMCP:
        def __init__(self) -> None:
            self.fns: dict[str, Any] = {}

        def tool(self, *args: Any, **kwargs: Any):
            def decorate(fn):
                self.fns[fn.__name__] = fn
                return fn

            return decorate

    mcp = FakeMCP()
    module.register_tools(mcp, **deps)  # type: ignore[arg-type]
    return mcp.fns


class _Drush:
    """Records the command line and answers with a canned result."""

    def __init__(self, result: dict[str, Any]):
        self.result = result
        self.calls: list[tuple[str, list[str]]] = []

    async def run(self, *parts: Any, **kwargs: Any):
        command = str(parts[0])
        args: list[str] = []
        for rest in parts[1:]:
            args.extend(rest if isinstance(rest, (list, tuple)) else [str(rest)])
        self.calls.append((command, args))
        return self.result


def test_user_roles_uses_a_drush_command_that_exists():
    """Drush 13 has no `user:role:list`; the sweep got 'is not defined'."""
    import asyncio

    drush = _Drush({"returncode": 0, "data": {"2": {"uid": "2", "name": "sam", "roles": ["authenticated"]}}})
    fns = _register("users", drush_client=drush)

    result = asyncio.run(fns["get_user_roles"]("2"))

    assert drush.calls[0][0] == "user:information"
    assert drush.calls[0][1] == ["--uid=2"]
    assert result["roles"] == ["authenticated"]
    assert result["name"] == "sam"


def test_permission_audit_falls_back_to_role_list():
    """Same rename: `user:role:list` -> `role:list`."""
    import asyncio

    drush = _Drush({"returncode": 0, "data": {"authenticated": {"rid": "authenticated", "perms": []}}})
    fns = _register("security_audit", drush_client=drush, jsonapi_client=None)

    result = asyncio.run(fns["permission_audit"]())

    assert drush.calls[0][0] == "role:list"
    assert "error" not in result


def test_queue_run_does_not_pretend_it_can_limit_the_run():
    """Drush 13 has neither --limit nor --count on queue:run; it drains the
    whole queue, so a claimed limit would be a lie."""
    import asyncio

    drush = _Drush({"returncode": 0, "data": {}})
    fns = _register("scheduler", drush_client=drush)

    result = asyncio.run(fns["queue_run"]("aggregator", limit=5))

    assert drush.calls[0] == ("queue:run", ["aggregator"])
    assert result["requested_limit"] == 5
    assert "no per-run limit" in result["note"]


def test_queue_info_reads_queue_list_and_names_the_known_queues():
    import asyncio

    drush = _Drush({"returncode": 0, "data": {"media_entity_thumbnail": {"items": 0}}})
    fns = _register("scheduler", drush_client=drush)

    found = asyncio.run(fns["queue_info"]("media_entity_thumbnail"))
    missing = asyncio.run(fns["queue_info"]("nope"))

    assert drush.calls[0][0] == "queue:list"
    assert found["info"] == {"items": 0}
    assert "No queue named 'nope'" in missing["error"]
    assert "media_entity_thumbnail" in missing["error"]


def test_composer_tools_run_the_composer_binary_not_drush(monkeypatch):
    """`drush composer ...` failed with 'Command "composer" is not defined'."""
    import asyncio

    import drupal_mcp_server.tools.devops as devops

    seen: list[list[str]] = []

    async def fake_composer(args: list[str]) -> dict[str, Any]:
        seen.append(args)
        return {"returncode": 0, "output": "ok"}

    monkeypatch.setattr(devops, "_run_composer", fake_composer, raising=True)
    fns = _register("devops", drush_client=None, site_manager=object())

    result = asyncio.run(fns["composer_install"](no_dev=True))

    assert seen == [["install", "--working-dir=.", "--no-dev", "--optimize-autoloader"]]
    assert result["returncode"] == 0
    # Composer is its own executable, so no Drush is needed for it.
    assert "Drush not available" not in str(result)


def test_composer_require_splits_several_packages(monkeypatch):
    """An agent asks for "these two modules" and got a version-parse error.

    The package string was handed to composer as one argv token, so composer
    read `drupal/pathauto` as a version constraint on `drupal/token`.
    """
    import asyncio

    import drupal_mcp_server.tools.devops as devops

    seen: list[list[str]] = []

    async def fake_composer(args: list[str]) -> dict[str, Any]:
        seen.append(args)
        return {"returncode": 0, "output": "ok"}

    monkeypatch.setattr(devops, "_run_composer", fake_composer, raising=True)
    fns = _register("devops", drush_client=None, site_manager=object())

    asyncio.run(fns["composer_require"]("drupal/token drupal/pathauto"))

    assert seen == [["require", "drupal/token", "drupal/pathauto", "--working-dir=."]]


def test_composer_require_applies_a_version_to_a_single_package(monkeypatch):
    import asyncio

    import drupal_mcp_server.tools.devops as devops

    seen: list[list[str]] = []

    async def fake_composer(args: list[str]) -> dict[str, Any]:
        seen.append(args)
        return {"returncode": 0, "output": "ok"}

    monkeypatch.setattr(devops, "_run_composer", fake_composer, raising=True)
    fns = _register("devops", drush_client=None, site_manager=object())

    # One package: the version pins it.
    asyncio.run(fns["composer_require"]("drupal/redirect", version="^3"))
    # Several: pinning each one identically would be wrong, so it is left off
    # and the caller gets composer's own resolution.
    asyncio.run(fns["composer_require"]("drupal/redirect drupal/metatag", version="^3"))

    assert seen[0] == ["require", "drupal/redirect:^3", "--working-dir=."]
    assert seen[1] == ["require", "drupal/redirect", "drupal/metatag", "--working-dir=."]


def test_composer_require_rejects_an_empty_package_list(monkeypatch):
    import asyncio

    import drupal_mcp_server.tools.devops as devops

    async def fake_composer(args: list[str]) -> dict[str, Any]:
        raise AssertionError("composer must not run with no packages")

    monkeypatch.setattr(devops, "_run_composer", fake_composer, raising=True)
    fns = _register("devops", drush_client=None, site_manager=object())

    result = asyncio.run(fns["composer_require"]("   "))

    assert "No package given" in result["error"]


def test_composer_runs_in_the_container_for_a_ddev_project(monkeypatch, tmp_path):
    """The host composer resolved against the host's PHP and took the site down.

    It locked in a `doctrine/collections` release needing PHP 8.4 for a
    container running 8.3, and Composer's platform check then aborted every
    subsequent request.
    """
    import drupal_mcp_server.tools._utils as tool_utils

    (tmp_path / ".ddev").mkdir()
    monkeypatch.setattr(tool_utils.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(tool_utils.os.path, "isdir", lambda p: str(p).endswith(".ddev"))

    argv = tool_utils._container_composer(
        ["require", "drupal/commerce", f"--working-dir={tmp_path}"]
    )

    assert argv == ["ddev", "composer"]


def test_composer_uses_lando_when_the_project_is_lando_managed(monkeypatch, tmp_path):
    import drupal_mcp_server.tools._utils as tool_utils

    lando = tmp_path / ".lando.yml"
    lando.write_text("name: site\n")
    monkeypatch.setattr(tool_utils.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(tool_utils.os.path, "isdir", lambda p: False)
    monkeypatch.setattr(tool_utils.os.path, "exists", lambda p: str(p).endswith(".lando.yml"))

    argv = tool_utils._container_composer(["require", "x", f"--working-dir={tmp_path}"])

    assert argv == ["lando", "composer"]


def test_composer_falls_back_to_a_local_binary_for_a_plain_project(monkeypatch, tmp_path):
    import drupal_mcp_server.tools._utils as tool_utils

    monkeypatch.setattr(tool_utils.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(tool_utils.os.path, "isdir", lambda p: False)
    monkeypatch.setattr(tool_utils.os.path, "exists", lambda p: False)

    argv = tool_utils._container_composer(["require", "x", f"--working-dir={tmp_path}"])

    assert argv is None


def test_composer_skips_the_container_when_the_tool_is_missing(monkeypatch, tmp_path):
    """A .ddev directory with no ddev binary must not produce a broken command."""
    import drupal_mcp_server.tools._utils as tool_utils

    (tmp_path / ".ddev").mkdir()
    monkeypatch.setattr(
        tool_utils.shutil, "which", lambda name: None if name == "ddev" else f"/usr/bin/{name}"
    )
    monkeypatch.setattr(tool_utils.os.path, "isdir", lambda p: str(p).endswith(".ddev"))

    argv = tool_utils._container_composer(["require", "x", f"--working-dir={tmp_path}"])

    assert argv is None


def test_composer_runner_reports_a_missing_composer(monkeypatch):
    import asyncio

    import drupal_mcp_server.tools._utils as tool_utils

    monkeypatch.setattr(tool_utils.shutil, "which", lambda name: None)
    monkeypatch.setattr(tool_utils.os.path, "exists", lambda path: False)

    result = asyncio.run(tool_utils.run_composer(["install"]))

    assert result["returncode"] == 127
    assert "composer is not on PATH" in result["error"]


def test_color_contrast_validates_hex_instead_of_raising():
    """Bad input produced `invalid literal for int() with base 10: 'sw'`."""
    import asyncio

    fns = _register("accessibility", drush_client=object(), jsonapi_client=None)

    bad = asyncio.run(fns["accessibility_color_contrast"]("sweep_value", "#fff"))
    good = asyncio.run(fns["accessibility_color_contrast"]("#000000", "#ffffff"))

    assert "hex colour" in bad["error"]
    assert "sweep_value" in bad["error"]
    assert good["ratio"] == 21.0
    assert good["aa_normal"] is True


def test_base64_media_rejects_payload_it_cannot_decode():
    import asyncio

    drush = _Drush({"returncode": 0, "data": {}})
    fns = _register("media_enhanced", drush_client=drush, jsonapi_client=None)

    result = asyncio.run(fns["media_create_from_base64"]("not!base64", "photo.png"))

    assert "not valid base64" in result["error"]
    assert "photo.png" in result["error"]
    assert drush.calls == []


def test_layout_builder_tools_call_php_eval_rather_than_a_missing_jsonapi_resource():
    """These tools used to request `/jsonapi/layout_builder`, which has never
    existed, and answer with a 404 whose only clue was the URL. They now talk
    to the real API through Drush."""
    import asyncio

    drush = _Drush({"returncode": 0, "data": {
        "display_id": "node.article.default", "enabled": True, "sections": [],
    }})
    fns = _register("layout_builder", drush_client=drush, jsonapi_client=None)

    result = asyncio.run(fns["layout_builder_get"]("node", "article"))

    command, args = drush.calls[0]
    assert command == "php:eval"
    php = args[0]
    assert "entity_view_display" in php
    # The display id is built from base64 parts, so a bundle with a quote or
    # a non-ASCII character cannot break out of the PHP string.
    assert _b64_text("node") in php and _b64_text("article") in php
    assert result["enabled"] is True


def _b64_text(value: str) -> str:
    import base64

    return base64.b64encode(value.encode()).decode()


def test_layout_builder_surfaces_a_failed_drush_run():
    """A failed drush command returns {returncode: 1, stderr} with no `error`
    key, which is exactly how ten tools reported a broken command as a
    success."""
    import asyncio

    drush = _Drush({
        "returncode": 1,
        "data": {},
        "stderr": "Error: Undefined variable $d in eval()",
    })
    fns = _register("layout_builder", drush_client=drush, jsonapi_client=None)

    result = asyncio.run(fns["layout_builder_get"]("node", "article"))

    assert "error" in result
    assert "Undefined variable" in result["error"]


def test_layout_builder_reports_php_that_does_not_print_json():
    """`data: {output: "..."}` means the script printed something that failed
    to parse; returning it as success would hide the message entirely."""
    import asyncio

    drush = _Drush({"returncode": 0, "data": {"output": "Fatal error: boom"}})
    fns = _register("layout_builder", drush_client=drush, jsonapi_client=None)

    result = asyncio.run(fns["layout_builder_get"]("node", "article"))

    assert "boom" in result["error"]


def test_layout_builder_needs_a_drush_client():
    import asyncio

    fns = _register("layout_builder", drush_client=None, jsonapi_client=None)

    result = asyncio.run(fns["layout_builder_get"]("node", "article"))

    assert result == {"error": "Drush not available"}


def test_section_add_embeds_the_spec_safely():
    """The spec reaches PHP as base64, so quotes and non-ASCII labels in a
    section survive the trip through the shell and the PHP parser."""
    import asyncio

    drush = _Drush({"returncode": 0, "data": {"section_count": 2}})
    fns = _register("layout_builder", drush_client=drush, jsonapi_client=None)

    spec = {"layout_id": "layout_onecol", "components": [
        {"plugin": "system_main_block", "region": "content"}
    ]}
    result = asyncio.run(fns["layout_builder_section_add"]("node", "article", spec))

    php = drush.calls[0][1][0]
    import base64
    import json as jsonlib

    encoded = jsonlib.dumps(spec)
    assert base64.b64encode(encoded.encode()).decode() in php
    assert "SectionComponent" in php and "appendSection" in php
    assert result["section_count"] == 2


def test_override_remove_can_target_one_entity_or_list_them():
    """Overrides live in the entity's `layout_builder__layout` field, not on
    the display, so the tool has to name an entity - or say which entities
    carry one."""
    import asyncio

    drush = _Drush({"returncode": 0, "data": {"overridden": ["3"]}})
    fns = _register("layout_builder", drush_client=drush, jsonapi_client=None)

    list_mode = asyncio.run(fns["layout_builder_override_remove"]("node", "article"))
    one = asyncio.run(fns["layout_builder_override_remove"]("node", "article", "3"))

    list_php = drush.calls[0][1][0]
    single_php = drush.calls[1][1][0]
    # Listing must not contain an entity id; targeting must.
    assert _b64_text("3") in single_php
    assert list_php != single_php
    assert list_mode["overridden"] == ["3"]
    assert one["overridden"] == ["3"]


# --- Filters on fields that do not exist ----------------------------------


class _JSONAPI:
    """Records the resource and params each tool asked for."""

    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self.result: dict[str, Any] = result or {"data": []}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_resource(self, resource: str, params: dict[str, Any] | None = None):
        self.calls.append((resource, params or {}))
        return self.result


def test_menu_link_list_filters_on_menu_name():
    """`menu_link_content` has no `menu` field. Filtering on it made Drupal
    answer 400 "Invalid nested filtering ... the field `menu`, given in the
    path `menu`, does not exist" on every call, on every site, so the tool
    never listed a single link when asked to filter."""
    import asyncio

    api = _JSONAPI({"data": [{"id": "a", "attributes": {"title": "Home"}}]})
    fns = _register("menus", jsonapi_client=api)

    result = asyncio.run(fns["menu_link_list"](menu_id="admin"))

    resource, params = api.calls[0]
    assert resource == "menu_link_content"
    assert "filter[menu]" not in params
    assert params["filter[menu_name]"] == "admin"
    assert "error" not in result


def test_menu_link_list_still_passes_caller_supplied_filters_through():
    """The `filters` argument is the caller's choice of field name."""
    import asyncio

    api = _JSONAPI()
    fns = _register("menus", jsonapi_client=api)

    asyncio.run(fns["menu_link_list"](filters={"title": "Home"}))

    assert api.calls[0][1]["filter[title]"] == "Home"


def test_permission_audit_filters_a_role_on_label():
    """`user_role` exposes `label`, not `name`. The `name` filter returned
    400 "Invalid nested filtering ... the field `name` ... does not exist"
    every time, so the role-specific branch of this tool never worked."""
    import asyncio

    api = _JSONAPI({"data": [{"id": "administrator", "attributes": {"label": "administrator"}}]})
    fns = _register("security_audit", jsonapi_client=api, drush_client=None)

    result = asyncio.run(fns["permission_audit"](role="administrator"))

    resource, params = api.calls[-1]
    assert resource == "user_role"
    assert "filter[name]" not in params
    assert params["filter[label]"] == "administrator"
    assert result["role"] == "administrator"


# --- drush_command option rendering ---------------------------------------
#
# `drush_command` rendered every option as `--key=value` whenever the value
# was truthy. Drush flags take no value, so the documented way to answer a
# confirmation -- `options={"yes": True}` -- became `--yes=True` and drush
# refused it: "The --yes option does not accept a value". Installing a module
# through the tool therefore failed every time while reporting success, and
# the live site silently kept every module uninstalled.


def test_drush_command_renders_a_true_option_as_a_bare_flag():
    """`--yes=True` is rejected by drush; the flag must carry no value."""
    import asyncio

    drush = _Drush({"returncode": 0, "data": {}, "stderr": ""})
    fns = _register("devops", drush_client=drush, site_manager=None)

    result = asyncio.run(fns["drush_command"](
        "pm:install", ["media"], {"yes": True},
    ))

    assert drush.calls[0] == ("pm:install", ["media", "--yes"])
    assert "error" not in result


def test_drush_command_omits_a_false_option_entirely():
    """A False means "do not pass this flag", not "--flag=False".

    It used to render as a bare `--yes`, which is the exact opposite of what
    the caller asked for and suppressed confirmation on destructive commands.
    """
    import asyncio

    drush = _Drush({"returncode": 0, "data": {}, "stderr": ""})
    fns = _register("devops", drush_client=drush, site_manager=None)

    asyncio.run(fns["drush_command"]("user:delete", ["1"], {"yes": False}))

    assert drush.calls[0] == ("user:delete", ["1"])


def test_drush_command_keeps_zero_valued_options():
    """`if v` treated 0 as absent, so `--limit=0` became a bare `--limit`."""
    import asyncio

    drush = _Drush({"returncode": 0, "data": {}, "stderr": ""})
    fns = _register("devops", drush_client=drush, site_manager=None)

    asyncio.run(fns["drush_command"]("watchdog:show", [], {"count": 0}))

    assert drush.calls[0] == ("watchdog:show", ["--count=0"])


def test_drush_command_keeps_valued_options_verbatim():
    import asyncio

    drush = _Drush({"returncode": 0, "data": {}, "stderr": ""})
    fns = _register("devops", drush_client=drush, site_manager=None)

    asyncio.run(fns["drush_command"]("pm:list", [], {"format": "json", "status": "enabled"}))

    assert drush.calls[0] == ("pm:list", ["--format=json", "--status=enabled"])


def test_drush_command_surfaces_a_failed_run_as_an_error():
    """The generic escape hatch returned the raw drush dict with no `error`.

    `ensure_dict` already fixes this for the 224 specialised call sites, but
    `drush_command` -- the tool an agent reaches for first -- bypassed it, so a
    command that exited non-zero looked like a success with empty data.
    """
    import asyncio

    drush = _Drush({
        "returncode": 1,
        "data": {},
        "stderr": "Failed to run drush pm:install media: exit status 1",
        "command": "ddev drush pm:install media --yes",
    })
    fns = _register("devops", drush_client=drush, site_manager=None)

    result = asyncio.run(fns["drush_command"]("pm:install", ["media"], {"yes": True}))

    assert "exit status 1" in result["error"]
    # The rest of the payload is preserved alongside the new key.
    assert result["returncode"] == 1
    assert result["command"].endswith("pm:install media --yes")


def test_langcode_is_only_sent_when_the_caller_asks_for_it():
    """A default of "en" made every create 403 on a multilingual site.

    Once a second language exists, `langcode` becomes a permission-gated
    field, so posting it unconditionally failed with "the current user is not
    allowed to POST the selected field (langcode)" for anyone who cannot
    translate -- including an ordinary authenticated user creating a term in
    the site's own language.
    """
    from drupal_mcp_server.tools._utils import langcode_field

    assert langcode_field(None) == {}
    assert langcode_field("") == {}
    assert langcode_field("fr") == {"langcode": "fr"}


def test_create_term_omits_langcode_unless_asked():
    import asyncio

    class _API:
        def __init__(self) -> None:
            self.payloads: list[dict[str, Any]] = []

        async def create_resource(self, resource: str, data: dict[str, Any]):
            self.payloads.append(data)
            return {"data": {"id": "1", "attributes": {}}}

    api = _API()
    fns = _register("taxonomy", jsonapi_client=api)

    asyncio.run(fns["create_term"]("tags", "one"))
    asyncio.run(fns["create_term"]("tags", "two", langcode="fr"))

    assert "langcode" not in api.payloads[0]
    assert api.payloads[1]["langcode"] == "fr"
