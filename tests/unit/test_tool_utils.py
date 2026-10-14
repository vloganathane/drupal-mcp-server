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
    """DDEV 1.24 rejects `kind:`; the key is `type:`."""
    import asyncio

    project = tmp_path / "my-site"
    result = asyncio.run(_register_devops(tmp_path)["ddev_setup"](str(project)))

    assert result["status"] == "created"
    written = (project / ".ddev" / "config.yaml").read_text()
    assert written == "name: my-site\ntype: drupal10\nwebroot: web\n"


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
