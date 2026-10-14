"""Tests for the shared tool helpers and for the DevOps setup tools."""

from pathlib import Path
from typing import Any

from drupal_mcp_server.tools._utils import drush_output, drush_result


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


def test_layout_builder_tools_stop_pretending_jsonapi_exposes_layouts():
    """`/jsonapi/layout_builder` never existed, so every one of these tools
    only ever produced a 404 with no explanation."""
    import asyncio

    fns = _register("layout_builder", drush_client=object(), jsonapi_client=object())

    got = asyncio.run(fns["layout_builder_get"]("node", "article"))
    added = asyncio.run(fns["layout_builder_section_add"]("node", "article", {}))

    for result in (got, added):
        assert "does not expose a JSON:API resource" in result["error"]
        assert result["entity_type"] == "node"
        assert "entity_view_display" in result["error"]


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
