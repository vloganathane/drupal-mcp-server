"""Batch 5 coverage: runner, scanner, and generator tools.

Ground truth verified against upstream sources this session (drush-ops/drush
13.x, behat/Behat, sebastianbergmann/phpunit): drush ships no ``php:unit``,
``behat:run``, ``nightwatch:run``, ``exec`` or ``composer`` command, and
``config:import`` accepts only ``--diff``/``--source``/``--partial`` --
so ``--preview`` (sync_config) and ``--skip-hash-check`` (import_config)
cannot exist. The tools pinned here used all of those, or wrote shell-era
``\\$`` escapes into PHP that reaches drush without a shell, or accepted
parameters they silently ignored.

The broken runners answered the live sweep "OK" because the failure landed
under a wrapped ``{"result": {"returncode": 1}}`` with no top-level
``error`` -- the sweep proves a tool answers, not that it succeeds. Every
test below was red against the previous behavior; each red failure is one
of these defects.
"""

import asyncio
import os
import re
import shutil
from typing import Any
from unittest.mock import MagicMock

import pytest

# --- harness ----------------------------------------------------------------


def _capture_tools(register_func, **deps):
    """Capture tool functions registered by a register_tools function."""
    mock_mcp = MagicMock()
    registered: list[Any] = []

    def tool_decorator():
        def wrapper(f):
            registered.append(f)
            return f

        return wrapper

    mock_mcp.tool = MagicMock(side_effect=tool_decorator)
    register_func(mock_mcp, **deps)
    return registered


def _find_tool(registered_tools, name):
    for tool in registered_tools:
        if tool.__name__ == name:
            return tool
    raise ValueError(f"Tool {name} not found among {len(registered_tools)} registered tools")


def _flat(args) -> list[str]:
    """Flatten run() argument parts (strings and nested lists) to argv tokens."""
    out: list[str] = []
    for part in args:
        if isinstance(part, (list, tuple)):
            out.extend(str(item) for item in part)
        else:
            out.append(str(part))
    return out


class FakeDrush:
    """Records run() calls; per-command scripted results, defaults to rc 0."""

    def __init__(self, script: dict[str, list[dict[str, Any]]] | None = None):
        self.script = {name: list(rows) for name, rows in (script or {}).items()}
        self.calls: list[dict[str, Any]] = []

    async def run(self, *parts, cwd=None, alias=None):
        command = str(parts[0])
        self.calls.append(
            {"command": command, "args": list(parts[1:]), "alias": alias, "cwd": cwd}
        )
        queue = self.script.get(command)
        if queue:
            return queue.pop(0)
        return {"returncode": 0, "data": {"output": "ok"}, "stderr": "", "command": command}


class _FakeProc:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", rc: int = 0):
        self._stdout, self._stderr, self.returncode = stdout, stderr, rc

    async def communicate(self):
        return self._stdout, self._stderr


def _record_procs(monkeypatch, results: list[_FakeProc] | None = None) -> list[list[str]]:
    """Patch subprocess creation; record argv, return scripted procs in order."""
    calls: list[list[str]] = []
    script = list(results or [])

    async def fake_exec(*argv, **kwargs):
        calls.append(list(argv))
        if script:
            return script.pop(0)
        return _FakeProc(stdout=b"ok\n")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    return calls


@pytest.fixture
def site_root(tmp_path, monkeypatch):
    """A fake site with vendor/bin and node_modules/.bin test binaries."""
    root = tmp_path / "site"
    (root / "vendor" / "bin").mkdir(parents=True)
    (root / "node_modules" / ".bin").mkdir(parents=True)
    for rel in ("vendor/bin/phpunit", "vendor/bin/behat", "node_modules/.bin/nightwatch"):
        binary = root / rel
        binary.write_text("#!/bin/sh\nexit 0\n")
        binary.chmod(0o755)
    monkeypatch.setenv("DRUPAL_ROOT", str(root))
    _clear_settings_cache()
    yield root
    # Leave no deleted tmp path in the settings cache for later tests.
    _clear_settings_cache()


def _clear_settings_cache():
    """get_settings() is lru_cached: a fixture's setenv is invisible to it."""
    from drupal_mcp_server.config import get_settings

    get_settings.cache_clear()


# --- testing.py: the runners ------------------------------------------------
#
# Drush 13 core (48 command classes) contains no php:unit/behat:run/
# nightwatch:run. The runners now execute the site's own binaries and do not
# need a drush client at all.


@pytest.mark.asyncio
async def test_phpunit_runner_invokes_the_sites_binary(site_root, monkeypatch):
    from drupal_mcp_server.tools import testing as mod

    calls = _record_procs(monkeypatch)
    # Registered with no dependencies: the runners must not require drush.
    run = _find_tool(_capture_tools(mod.register_tools), "test_run_phpunit")

    result = await run(
        test_path="tests/src/Kernel/FooTest.php",
        group="core",
        filter="bar",
        coverage=True,
    )

    assert "error" not in result, result
    assert result["returncode"] == 0
    assert calls[0] == [
        str(site_root / "vendor" / "bin" / "phpunit"),
        "tests/src/Kernel/FooTest.php",
        "--group",
        "core",
        "--filter",
        "bar",
        "--coverage-html",
        "coverage",
    ]


@pytest.mark.asyncio
async def test_phpunit_runner_reports_a_missing_binary(monkeypatch):
    from drupal_mcp_server.tools import testing as mod

    monkeypatch.delenv("DRUPAL_ROOT", raising=False)
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    _clear_settings_cache()
    run = _find_tool(_capture_tools(mod.register_tools), "test_run_phpunit")

    result = await run()

    assert "error" in result, result
    assert "phpunit" in result["error"]
    assert "DRUPAL_ROOT" in result["error"]


@pytest.mark.asyncio
async def test_kernel_runner_requests_the_kernel_suite(site_root, monkeypatch):
    from drupal_mcp_server.tools import testing as mod

    calls = _record_procs(monkeypatch)
    run = _find_tool(_capture_tools(mod.register_tools), "test_run_kernel")

    result = await run(test_path="tests/src/FooTest.php")

    assert "error" not in result, result
    assert calls[0][0] == str(site_root / "vendor" / "bin" / "phpunit")
    # Suite names are exact: Drupal's phpunit.xml.dist defines "Kernel".
    assert "--testsuite=Kernel" in calls[0]
    assert "tests/src/FooTest.php" in calls[0]


@pytest.mark.asyncio
async def test_behat_runner_invokes_the_sites_behat(site_root, monkeypatch):
    from drupal_mcp_server.tools import testing as mod

    calls = _record_procs(monkeypatch)
    run = _find_tool(_capture_tools(mod.register_tools), "test_run_behat")

    result = await run(profile="ci", format="junit", tags="@smoke")

    assert "error" not in result, result
    assert calls[0] == [
        str(site_root / "vendor" / "bin" / "behat"),
        "--profile",
        "ci",
        "--format",
        "junit",
        "--tags",
        "@smoke",
    ]


@pytest.mark.asyncio
async def test_nightwatch_runner_invokes_node_modules_binary(site_root, monkeypatch):
    from drupal_mcp_server.tools import testing as mod

    calls = _record_procs(monkeypatch)
    run = _find_tool(_capture_tools(mod.register_tools), "test_run_nightwatch")

    result = await run(test_path="tests/e2e", env="chrome")

    assert "error" not in result, result
    assert calls[0] == [
        str(site_root / "node_modules" / ".bin" / "nightwatch"),
        "--env",
        "chrome",
        "tests/e2e",
    ]


@pytest.mark.asyncio
async def test_list_suites_asks_phpunit_not_drush(site_root, monkeypatch):
    from drupal_mcp_server.tools import testing as mod

    calls = _record_procs(monkeypatch)
    run = _find_tool(_capture_tools(mod.register_tools), "test_list_suites")

    result = await run()

    assert "error" not in result, result
    assert calls[0] == [str(site_root / "vendor" / "bin" / "phpunit"), "--list-suites"]


@pytest.mark.asyncio
async def test_coverage_report_validates_its_format(site_root, monkeypatch):
    from drupal_mcp_server.tools import testing as mod

    calls = _record_procs(monkeypatch)
    run = _find_tool(_capture_tools(mod.register_tools), "test_coverage_report")

    bad = await run(format="../../evil")
    assert "error" in bad and "coverage format" in bad["error"], bad
    assert calls == [], "a rejected format must not run anything"

    good = await run(format="clover", output_dir="out")
    assert "error" not in good, good
    assert calls[0][1:] == ["--coverage-clover", "out"]


@pytest.mark.asyncio
async def test_runner_surfaces_a_failing_binary(site_root, monkeypatch):
    from drupal_mcp_server.tools import testing as mod

    _record_procs(
        monkeypatch,
        [_FakeProc(stderr=b"PHPUnit: no tests found", rc=1)],
    )
    run = _find_tool(_capture_tools(mod.register_tools), "test_run_phpunit")

    result = await run()

    assert "error" in result, result
    assert "no tests found" in result["error"]
    assert result["returncode"] == 1


# --- performance.py ---------------------------------------------------------
#
# drush has no `exec` command: php:eval is the command that evaluates code,
# and it receives argv directly (no shell), so shell-era \$ escapes would
# reach PHP as literal backslashes.


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name", ["performance_cache_stats", "performance_redis_info", "performance_memcached_stats"]
)
async def test_backend_stats_run_php_eval_with_plain_php(name):
    from drupal_mcp_server.tools import performance as mod

    drush = FakeDrush()
    tool = _find_tool(_capture_tools(mod.register_tools, drush_client=drush), name)

    result = await tool()

    assert "error" not in result, result
    call = drush.calls[0]
    assert call["command"] == "php:eval"
    code = _flat(call["args"])[0]
    assert "\\$" not in code, "no shell eats the backslash before PHP"
    assert "$" in code


@pytest.mark.asyncio
async def test_query_log_refuses_a_duration_filter_watchdog_cannot_honor():
    from drupal_mcp_server.tools import performance as mod

    drush = FakeDrush()
    tool = _find_tool(_capture_tools(mod.register_tools, drush_client=drush), "performance_query_log")

    result = await tool(min_duration=2.0)

    assert "error" in result, result
    assert "duration" in result["error"]
    assert drush.calls == [], "a parameter that cannot be honored must refuse, not silently drop"


@pytest.mark.asyncio
async def test_query_log_builds_the_query_and_surfaces_php_failures():
    from drupal_mcp_server.tools import performance as mod

    drush = FakeDrush(
        {
            "php:eval": [
                {
                    "returncode": 1,
                    "data": {},
                    "stderr": "PHP Parse error: syntax error",
                    "command": "php:eval",
                }
            ]
        }
    )
    tool = _find_tool(_capture_tools(mod.register_tools, drush_client=drush), "performance_query_log")

    result = await tool(limit=5)

    assert drush.calls[0]["command"] == "php:eval"
    code = _flat(drush.calls[0]["args"])[0]
    assert "->range(0, 5)" in code
    assert "error" in result and "Parse error" in result["error"], result


@pytest.mark.asyncio
async def test_query_log_validates_limit():
    from drupal_mcp_server.tools import performance as mod

    drush = FakeDrush()
    tool = _find_tool(_capture_tools(mod.register_tools, drush_client=drush), "performance_query_log")

    result = await tool(limit=0)

    assert "error" in result and drush.calls == []


@pytest.mark.asyncio
async def test_page_load_url_is_quoted_for_php_not_interpolated():
    from drupal_mcp_server.tools import performance as mod

    drush = FakeDrush()
    tool = _find_tool(
        _capture_tools(mod.register_tools, drush_client=drush), "performance_page_load_analyze"
    )

    result = await tool(url="http://example.test/page?q=a'b")

    assert "error" not in result, result
    call = drush.calls[0]
    assert call["command"] == "php:eval"
    code = _flat(call["args"])[0]
    assert "get('http://example.test/page?q=a\\'b')" in code
    assert "get('http://example.test/page?q=a'b')" not in code, "a raw quote ends the PHP literal"


@pytest.mark.asyncio
async def test_page_load_rejects_non_http_urls():
    from drupal_mcp_server.tools import performance as mod

    drush = FakeDrush()
    tool = _find_tool(
        _capture_tools(mod.register_tools, drush_client=drush), "performance_page_load_analyze"
    )

    result = await tool(url="file:///etc/passwd")

    assert "error" in result and drush.calls == []


@pytest.mark.asyncio
async def test_bigpipe_tools_use_real_config_commands():
    from drupal_mcp_server.tools import performance as mod

    drush = FakeDrush()
    tools = _capture_tools(mod.register_tools, drush_client=drush)

    status = await _find_tool(tools, "performance_bigpipe_status")()
    enable = await _find_tool(tools, "performance_bigpipe_enable")(enable=True)

    assert "error" not in status and "error" not in enable
    assert drush.calls[0]["command"] == "config:get"
    assert drush.calls[1]["command"] == "config:set"
    assert _flat(drush.calls[1]["args"]) == ["bigpipe.settings", "enabled", "true"]


# --- accessibility_report_generate ------------------------------------------
#
# Same `exec` defect as performance.py, plus the axe class name carried
# doubled backslashes (\\Deque\\Axe\\Axe) that PHP reads as a literal
# backslash, and the URL was interpolated raw into a PHP single-quoted
# literal.


@pytest.mark.asyncio
async def test_accessibility_report_runs_axe_through_php_eval(tmp_path):
    from drupal_mcp_server.tools import accessibility as mod

    drush = FakeDrush()
    tool = _find_tool(
        _capture_tools(mod.register_tools, drush_client=drush), "accessibility_report_generate"
    )

    result = await tool(
        urls=["https://site.test/p'a"], output_dir=str(tmp_path / "report")
    )

    assert "error" not in result, result
    call = drush.calls[0]
    assert call["command"] == "php:eval"
    code = _flat(call["args"])[0]
    assert "new \\Deque\\Axe\\Axe()" in code
    assert "\\\\Deque" not in code, "PHP class names take single backslashes"
    assert "analyze('https://site.test/p\\'a')" in code
    assert result["pages_analyzed"] == 1
    assert os.path.exists(result["report_file"])


@pytest.mark.asyncio
async def test_accessibility_report_surfaces_a_failing_axe_run(tmp_path):
    from drupal_mcp_server.tools import accessibility as mod

    drush = FakeDrush(
        {
            "php:eval": [
                {
                    "returncode": 1,
                    "data": {},
                    "stderr": "Class 'Deque\\Axe\\Axe' not found",
                    "command": "php:eval",
                }
            ]
        }
    )
    tool = _find_tool(
        _capture_tools(mod.register_tools, drush_client=drush), "accessibility_report_generate"
    )

    result = await tool(urls=["https://site.test/"], output_dir=str(tmp_path / "rep"))

    assert "error" in result, result
    assert "not found" in result["error"]


# --- security_audit.py ------------------------------------------------------


@pytest.mark.asyncio
async def test_dependency_scan_runs_composer_directly(monkeypatch):
    from drupal_mcp_server.tools import security_audit as mod

    composer_calls: list[list[str]] = []

    async def fake_composer(args, **kwargs):
        composer_calls.append(list(args))
        return {"returncode": 0, "output": "{}", "command": "composer " + " ".join(args)}

    monkeypatch.setattr(mod, "_run_composer", fake_composer)
    drush = FakeDrush()
    tool = _find_tool(_capture_tools(mod.register_tools, drush_client=drush), "dependency_scan")

    result = await tool()

    assert "error" not in result, result
    assert drush.calls == [], "drush has no composer command"
    assert composer_calls[0][:2] == ["audit", "--format=json"]
    assert composer_calls[1][:2] == ["show", "roave/security-advisories"]


@pytest.mark.asyncio
async def test_dependency_scan_does_not_need_drush(monkeypatch):
    from drupal_mcp_server.tools import security_audit as mod

    async def fake_composer(args, **kwargs):
        return {"returncode": 0, "output": "{}", "command": "composer"}

    monkeypatch.setattr(mod, "_run_composer", fake_composer)
    tool = _find_tool(_capture_tools(mod.register_tools), "dependency_scan")

    result = await tool()

    assert "error" not in result, result


@pytest.mark.asyncio
async def test_file_permissions_audit_rejects_quotes_in_the_path():
    from drupal_mcp_server.tools import security_audit as mod

    drush = FakeDrush()
    tool = _find_tool(
        _capture_tools(mod.register_tools, drush_client=drush), "file_permissions_audit"
    )

    result = await tool(path="public://x'); system('id'); //")

    assert "error" in result, result
    assert drush.calls == [], "the prefix allowlist alone leaves the suffix injectable"


@pytest.mark.asyncio
async def test_file_permissions_audit_allows_plain_stream_paths():
    from drupal_mcp_server.tools import security_audit as mod

    drush = FakeDrush()
    tool = _find_tool(
        _capture_tools(mod.register_tools, drush_client=drush), "file_permissions_audit"
    )

    result = await tool(path="public://css/site.css")

    assert "error" not in result, result
    call = drush.calls[0]
    assert call["command"] == "ev"
    assert _flat(call["args"])[0] == (
        "echo is_dir('public://css/site.css') ? 'exists' : 'not found';"
    )


def test_php_single_quote_escapes_quotes_and_backslashes():
    from drupal_mcp_server.tools._utils import php_single_quote

    assert php_single_quote("a'b") == "'a\\'b'"
    assert php_single_quote("a\\b") == "'a\\\\b'"
    assert php_single_quote("plain") == "'plain'"


# --- headless.py ------------------------------------------------------------


@pytest.mark.asyncio
async def test_nextjs_helpers_generate_without_any_client(tmp_path):
    from drupal_mcp_server.tools import headless as mod

    # Registered with no deps: the generator only needs the entity names it
    # was given, so neither drush nor JSON:API is a precondition.
    tool = _find_tool(_capture_tools(mod.register_tools), "nextjs_helpers_generate")

    result = await tool(entity_types=["node--article"], output_dir=str(tmp_path / "nx"))

    assert "error" not in result, result
    assert result["generated"] == ["node--article"]


@pytest.mark.asyncio
async def test_nextjs_helpers_emit_valid_identifiers_and_paths(tmp_path):
    from drupal_mcp_server.tools import headless as mod

    out = tmp_path / "nx"
    tool = _find_tool(_capture_tools(mod.register_tools), "nextjs_helpers_generate")

    await tool(entity_types=["node--article"], output_dir=str(out))

    types_src = (out / "drupal-types.ts").read_text()
    api_src = (out / "drupal-api.ts").read_text()
    assert "export interface DrupalNodeArticle {" in types_src
    assert "Node--" not in types_src, "dashes cannot appear in a TS identifier"
    assert "export async function getNodeArticle(id: string)" in api_src
    # JSON:API type strings are not URL paths: node--article lives at
    # /jsonapi/node/article.
    assert "/jsonapi/node/article/${id}" in api_src
    assert re.search(r"interface\s+[A-Za-z][A-Za-z0-9]*\s", types_src)


@pytest.mark.asyncio
async def test_gatsby_config_points_at_the_configured_site(tmp_path):
    from drupal_mcp_server.tools import headless as mod

    class _API:
        _base_url = "https://cms.example.test"

    out = tmp_path / "gatsby"
    tool = _find_tool(
        _capture_tools(mod.register_tools, jsonapi_client=_API(), drush_client=FakeDrush()),
        "gatsby_helpers_generate",
    )

    result = await tool(entity_types=["node--article"], output_dir=str(out))

    assert "error" not in result, result
    config_js = (out / "gatsby-config.js").read_text()
    assert '"baseUrl": "https://cms.example.test"' in config_js
    assert '"apiBase": "jsonapi"' in config_js


@pytest.mark.asyncio
async def test_graphql_schema_extend_refuses_when_the_site_has_no_config():
    from drupal_mcp_server.tools import headless as mod

    drush = FakeDrush(
        {
            "config:get": [
                {
                    "returncode": 1,
                    "data": {},
                    "stderr": "Config graphql.schema.customization does not exist",
                    "command": "config:get",
                }
            ]
        }
    )
    tool = _find_tool(_capture_tools(mod.register_tools, drush_client=drush), "graphql_schema_extend")

    result = await tool(type_name="Comment", fields={"latest": "type"})

    assert "error" in result, result
    assert "graphql.schema.customization" in result["error"]
    assert all(call["command"] != "config:set" for call in drush.calls), (
        "the previous tool config:set a whole document with two arguments "
        "(config:set needs config, key, value) and failed on every call"
    )


@pytest.mark.asyncio
async def test_graphql_schema_extend_sets_keys_when_the_config_exists():
    from drupal_mcp_server.tools import headless as mod

    ok = {"returncode": 0, "data": {}, "stderr": "", "command": ""}
    drush = FakeDrush({"config:get": [ok], "config:set": [ok, ok]})
    tool = _find_tool(_capture_tools(mod.register_tools, drush_client=drush), "graphql_schema_extend")

    result = await tool(type_name="Comment", fields={"latest": "type"})

    assert "error" not in result, result
    sets = [call for call in drush.calls if call["command"] == "config:set"]
    assert _flat(sets[0]["args"])[0:2] == ["graphql.schema.customization", "extend_type"]
    assert _flat(sets[1]["args"])[0:2] == ["graphql.schema.customization", "fields"]
    assert "--input-format=json" in _flat(sets[1]["args"])


# --- generate_test_content --------------------------------------------------


class _ContentAPI:
    def __init__(self):
        self.created: list[tuple[str, dict[str, Any]]] = []

    async def create_resource(self, rtype, payload):
        self.created.append((rtype, payload))
        return {"data": {"id": f"n{len(self.created)}"}}


@pytest.mark.asyncio
async def test_generate_test_content_validates_count():
    from drupal_mcp_server.tools import content as mod

    api = _ContentAPI()
    tool = _find_tool(_capture_tools(mod.register_tools, jsonapi_client=api), "generate_test_content")

    for bad in (0, -3, 10_000):
        result = await tool(bundle="article", count=bad)
        assert "error" in result, (bad, result)
        assert "count" in result["error"]
    assert api.created == [], "an out-of-range count must refuse, not loop"

    ok = await tool(bundle="article", count=2)
    assert ok["generated"] == 2
    assert len(api.created) == 2
    assert all(rtype == "node--article" for rtype, _ in api.created)


# --- config.py --------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_config_exports_from_source_and_imports_into_target():
    from drupal_mcp_server.tools import config as mod

    drush = FakeDrush()
    tool = _find_tool(_capture_tools(mod.register_tools, drush_client=drush), "sync_config")

    result = await tool(source_env="staging", target_env="prod")

    assert "error" not in result, result
    export, import_ = drush.calls
    assert export["command"] == "config-export"
    assert export["alias"] == "@staging", "source_env used to be echoed but never applied"
    assert import_["command"] == "config-import"
    assert import_["alias"] == "@prod"
    assert "--source=/tmp/config_sync_source" in _flat(import_["args"])


@pytest.mark.asyncio
async def test_sync_config_dry_run_previews_via_config_status():
    from drupal_mcp_server.tools import config as mod

    drush = FakeDrush(
        {
            "config:status": [
                {
                    "returncode": 0,
                    "data": {"system.site": {"state": "Different"}},
                    "stderr": "",
                    "command": "config:status",
                }
            ]
        }
    )
    tool = _find_tool(_capture_tools(mod.register_tools, drush_client=drush), "sync_config")

    result = await tool(source_env="staging", target_env="prod", dry_run=True)

    assert result.get("dry_run") is True
    assert "changes_preview" in result
    assert "error" not in result, result
    status = drush.calls[-1]
    assert status["command"] == "config:status" and status["alias"] == "@prod"
    assert not any(
        "--preview" in str(arg) for call in drush.calls for arg in _flat(call["args"])
    ), "drush config:import has no --preview option (drush 13: --diff/--source/--partial)"


@pytest.mark.asyncio
async def test_sync_config_requires_drush():
    from drupal_mcp_server.tools import config as mod

    tool = _find_tool(_capture_tools(mod.register_tools), "sync_config")
    result = await tool(source_env="staging", target_env="prod")
    assert "error" in result


@pytest.mark.asyncio
async def test_diff_config_exports_each_environment_with_its_own_alias():
    from drupal_mcp_server.tools import config as mod

    drush = FakeDrush()
    tool = _find_tool(_capture_tools(mod.register_tools, drush_client=drush), "diff_config")

    result = await tool(config_name="system.site", env1="staging", env2="prod")

    assert "error" not in result, result
    first, second = drush.calls[0], drush.calls[1]
    assert first["command"] == "config-export" and first["alias"] == "@staging"
    assert second["command"] == "config-export" and second["alias"] == "@prod", (
        "both exports used to run against the active site, so the diff "
        "compared a directory with itself"
    )


@pytest.mark.asyncio
async def test_import_config_refuses_the_flag_drush_does_not_have():
    from drupal_mcp_server.tools import config as mod

    drush = FakeDrush()
    tool = _find_tool(_capture_tools(mod.register_tools, drush_client=drush), "import_config")

    refused = await tool(import_path="./cfg", skip_hash_check=True)
    assert "error" in refused, refused
    assert "--skip-hash-check" in refused["error"]
    assert "config:import" in refused["error"]
    assert drush.calls == [], "an option that does not exist must refuse, not fail at drush"

    ok = await tool(import_path="./cfg")
    assert "error" not in ok, ok
    assert drush.calls[-1]["command"] == "config-import"
    assert "--source=./cfg" in _flat(drush.calls[-1]["args"])


@pytest.mark.asyncio
async def test_split_config_writes_split_files_and_reports_missing(tmp_path):
    import yaml

    from drupal_mcp_server.tools import config as mod

    source = tmp_path / "sync"
    source.mkdir()
    (source / "system.site.yml").write_text(yaml.dump({"uuid": "abc", "langcode": "en"}))
    out = tmp_path / "split"
    tool = _find_tool(_capture_tools(mod.register_tools), "split_config")

    result = await tool(
        config_names=["system.site", "node.type.missing"],
        output_dir=str(out),
        source_dir=str(source),
    )

    assert result["total_split"] == 1
    assert result["missing_configs"] == ["node.type.missing"]
    assert (out / "system.site.yml").exists()
    assert (out / "system.site.yml").read_text() == (source / "system.site.yml").read_text()

    missing = await tool(config_names=["system.site"], output_dir=str(out), source_dir=str(tmp_path / "nope"))
    assert "error" in missing


# --- devops.py: sound pins --------------------------------------------------


@pytest.mark.asyncio
async def test_drush_cron_runs_cron_and_surfaces_failures():
    from drupal_mcp_server.tools import devops as mod

    drush = FakeDrush(
        {
            "cron": [
                {"returncode": 1, "data": {}, "stderr": "cron exploded", "command": "cron"}
            ]
        }
    )
    tool = _find_tool(_capture_tools(mod.register_tools, drush_client=drush), "drush_cron")

    failed = await tool()
    assert drush.calls[0]["command"] == "cron"
    assert "error" in failed and "cron exploded" in failed["error"], failed

    ok = await tool()
    assert "error" not in ok, ok


@pytest.mark.asyncio
async def test_drush_watchdog_builds_filter_arguments():
    from drupal_mcp_server.tools import devops as mod

    drush = FakeDrush()
    tool = _find_tool(_capture_tools(mod.register_tools, drush_client=drush), "drush_watchdog")

    result = await tool(count=10, type_filter="php", severity="Error")

    assert "error" not in result, result
    call = drush.calls[0]
    assert call["command"] == "watchdog:show"
    assert _flat(call["args"]) == ["--count=10", "--type=php", "--severity=Error"]


# --- feeds.py / contact.py / axe_scan: `exec` siblings ----------------------
#
# grep for `["exec",` after the performance fixes found these using the same
# nonexistent drush command; they fail identically on a real call and answer
# identically "OK" to the sweep.


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("feeds_parser_list", "parsers"),
        ("feeds_fetcher_list", "fetchers"),
        ("feeds_processor_list", "processors"),
    ],
)
async def test_feeds_plugin_listers_run_php_eval(name, key):
    from drupal_mcp_server.tools import feeds as mod

    drush = FakeDrush()
    tool = _find_tool(_capture_tools(mod.register_tools, drush_client=drush), name)

    result = await tool()

    assert "error" not in result, result
    call = drush.calls[0]
    assert call["command"] == "php:eval"
    code = _flat(call["args"])[0]
    assert "\\$" not in code, "no shell eats the backslash before PHP"
    assert key in result


@pytest.mark.asyncio
async def test_contact_spam_check_runs_php_eval_and_validates_id():
    from drupal_mcp_server.tools import contact as mod

    drush = FakeDrush(
        {
            "php:eval": [
                {
                    "returncode": 1,
                    "data": {},
                    "stderr": "Service contact.spam does not exist.",
                    "command": "php:eval",
                }
            ]
        }
    )
    tool = _find_tool(_capture_tools(mod.register_tools, drush_client=drush), "contact_spam_check")

    result = await tool(message_id="msg-1")

    assert drush.calls[0]["command"] == "php:eval"
    assert "\\$" not in _flat(drush.calls[0]["args"])[0]
    assert "error" in result and "does not exist" in result["error"], (
        "a failing eval must surface as an error, not a wrapped result"
    )

    refused = await tool(message_id="x'); phpinfo(); //")
    assert "error" in refused
    assert len(drush.calls) == 1, "an invalid id must refuse before any eval"


@pytest.mark.asyncio
async def test_axe_scan_runs_php_eval_with_quoted_url(site_root):
    from drupal_mcp_server.tools import accessibility as mod

    drush = FakeDrush()
    tool = _find_tool(_capture_tools(mod.register_tools, drush_client=drush), "accessibility_axe_scan")

    result = await tool(url="https://site.test/p'a")

    assert "error" not in result, result
    call = drush.calls[0]
    assert call["command"] == "php:eval"
    code = _flat(call["args"])[0]
    assert "new \\Deque\\Axe\\Axe()" in code
    assert "\\\\Deque" not in code
    assert "analyze('https://site.test/p\\'a')" in code
    # The autoload path must not depend on where the server was started.
    assert str(site_root / "vendor" / "autoload.php") in code


# --- DrushClient: per-call alias -------------------------------------------


def _client_settings(alias: str):
    class S:
        DRUSH_PATH = "drush"
        DRUSH_ALIAS = alias

    return S()


@pytest.mark.asyncio
async def test_run_applies_a_per_call_alias(monkeypatch):
    import drupal_mcp_server.clients.drush as drush_mod

    calls = _record_procs(monkeypatch)
    client = drush_mod.DrushClient(_client_settings("@self"))

    await client.run("config-export", ["--destination=/tmp/x"], alias="@staging")

    argv = calls[0]
    assert "@staging" in argv and "@self" not in argv
    assert argv.index("@staging") < argv.index("config-export")


@pytest.mark.asyncio
async def test_run_keeps_the_configured_alias_without_an_override(monkeypatch):
    import drupal_mcp_server.clients.drush as drush_mod

    calls = _record_procs(monkeypatch)
    client = drush_mod.DrushClient(_client_settings("@self"))

    await client.run("cron")

    assert "@self" in calls[0]
