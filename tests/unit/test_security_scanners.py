"""Unit tests for the local security scanners added in Wave 5.

The contract under test: a zero-dependency pattern pass (no PHPStan
required) with Drupal-aware false-positive suppression, targets confined
to DRUPAL_ROOT (contrib and tests/ pruned from the default scan, symlinks
skipped), counts that stay complete when the findings list truncates, and
routing classification where "no access requirement" is reported rather
than assumed safe.
"""

import asyncio
from pathlib import Path
from typing import Any

import drupal_mcp_server.tools.security_audit as security_audit


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


_VULN_MODULE = """<?php
/**
 * @file
 * Fixture module for scanner tests.
 */

// password = "supersecret123456"

function vulnmod_names($name) {
  print $name;
}

function vulnmod_query($name, $id) {
  return db_query("SELECT * FROM users WHERE name = '" . $name . "'", [':id' => $id]);
}

function vulnmod_safe($id) {
  return db_query('SELECT * FROM users WHERE uid = :uid', [':uid' => $id]);
}

function vulnmod_cmd_raw($dir) {
  return system("ls " . $dir);
}

function vulnmod_cmd_escaped($dir) {
  return system("ls " . escapeshellarg($dir));
}

function vulnmod_read($file) {
  $data = file_get_contents($_GET['file']);
  return $data;
}

function vulnmod_key() {
  $api_key = "abcdefghijklmnop12345678";
  return $api_key;
}

function vulnmod_eval($code) {
  eval($code);
}

function vulnmod_flash($message) {
  drupal_set_message($message, t('Saved'));
}

function vulnmod_label($name) {
  print t('Hello @name', ['@name' => $name]);
}
"""

_CONTROLLER = """<?php

namespace Drupal\\vulnmod\\Controller;

class Foo {

    public function page() {
        return ['#markup' => 'ok'];
    }

    public function open() {
        return ['#markup' => 'ok'];
    }
}
"""

_ROUTING = """vulnmod.public:
  path: '/vulnmod/public'
  defaults:
    _controller: '\\Drupal\\vulnmod\\Controller\\Foo::page'
  access: 'TRUE'
vulnmod.admin:
  path: '/vulnmod/admin'
  defaults:
    _controller: '\\Drupal\\vulnmod\\Controller\\Foo::admin'
  requirements:
    _permission: 'administer vulnmod'
vulnmod.custom:
  path: '/vulnmod/custom'
  defaults:
    _form: '\\Drupal\\vulnmod\\Form\\CustomForm'
  requirements:
    _custom_access: '\\Drupal\\vulnmod\\Form\\CustomForm::access'
vulnmod.open:
  path: '/vulnmod/open'
  defaults:
    _controller: '\\Drupal\\vulnmod\\Controller\\Foo::open'
vulnmod.legacy:
  alias: 'vulnmod.public'
vulnmod.entity_form:
  path: '/vulnmod/entity-form'
  defaults:
    _entity_form: 'vulnmod.add'
  requirements:
    _vulnmod_entity_create: 'vulnmod'
"""

_TESTED_BUT_PRUNED = "<?php\nprint $secret_value;\n"

_CONTRIB_MODULE = """<?php
function fine_things($data) {
  print $data;
}
"""


def _make_root(root: Path) -> Path:
    """A docroot with one custom module, one contrib module, and noise."""
    vulnmod = root / "modules" / "custom" / "vulnmod"
    (vulnmod / "src" / "Controller").mkdir(parents=True)
    (vulnmod / "tests").mkdir()
    (vulnmod / "vulnmod.module").write_text(_VULN_MODULE, encoding="utf-8")
    (vulnmod / "src" / "Controller" / "Foo.php").write_text(_CONTROLLER, encoding="utf-8")
    (vulnmod / "vulnmod.routing.yml").write_text(_ROUTING, encoding="utf-8")
    (vulnmod / "tests" / "helper.php").write_text(_TESTED_BUT_PRUNED, encoding="utf-8")
    fine = root / "modules" / "contrib" / "fine"
    fine.mkdir(parents=True)
    (fine / "fine.module").write_text(_CONTRIB_MODULE, encoding="utf-8")
    return vulnmod


def _fns(monkeypatch: Any, tmp_path: Path) -> dict[str, Any]:
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
    _make_root(root)
    monkeypatch.setattr(
        security_audit, "get_settings", lambda: _Settings(str(root))
    )
    return _tool_functions(security_audit)


def _pairs(result: dict[str, Any]) -> set[tuple[str, str]]:
    return {(row["category"], row["pattern"]) for row in result["findings"]}


# --- code_security_scan ----------------------------------------------------

def test_scan_finds_patterns_with_false_positives_suppressed(
    monkeypatch: Any, tmp_path: Path
) -> None:
    fns = _fns(monkeypatch, tmp_path)
    result = asyncio.run(fns["code_security_scan"](module="vulnmod"))

    assert result["files_scanned"] == 2  # tests/ pruned, routing.yml not code
    assert result["target"] == {"module": "vulnmod", "path": None}
    assert _pairs(result) == {
        ("xss", "unescaped_print"),
        ("sql_injection", "db_query_concat"),
        ("sql_injection", "sql_concat"),
        ("command_injection", "exec_with_variable"),
        ("path_traversal", "file_read_variable"),
        ("hardcoded_secrets", "api_key_hardcoded"),
        ("deprecated_api", "eval_usage"),
        ("deprecated_api", "drupal7_functions"),
    }
    # The three suppressed lines: commented password, escapeshellarg
    # command, and the XSS reading of drupal_set_message wrapped in t().
    # The same drupal_set_message line still counts as deprecated_api —
    # suppressing one pattern must not silence the other finding it earns.
    assert result["false_positives_filtered"] == 3
    assert result["counts"]["by_category"] == {
        "xss": 1,
        "sql_injection": 2,
        "command_injection": 1,
        "path_traversal": 1,
        "hardcoded_secrets": 1,
        "deprecated_api": 4,
    }
    assert result["counts"]["by_severity"] == {"high": 7, "medium": 3}
    assert result["truncated"] is False
    assert "note" not in result

    # Sorted by severity, and the suppressed lines never appear as XSS.
    severities = [row["severity"] for row in result["findings"]]
    assert severities == sorted(severities, key=lambda s: {"high": 0, "medium": 1, "low": 2}[s])
    snippets = [row["snippet"] for row in result["findings"]]
    assert not any("escapeshellarg" in s for s in snippets)
    assert not any(s.strip().startswith("//") for s in snippets)
    xss_rows = [row for row in result["findings"] if row["category"] == "xss"]
    assert not any("drupal_set_message" in row["snippet"] for row in xss_rows)
    # `t(` is not a Drupal 7 leftover: a plain translation call earns no
    # finding at all (the print t(...) fixture line).
    assert not any("print t(" in s for s in snippets)
    # Findings carry the remediation an agent can act on.
    for row in result["findings"]:
        assert row["file"].startswith("modules/custom/vulnmod/")
        assert row["line"] > 0
        assert row["recommendation"]
        assert row["description"]


def test_scan_default_target_skips_contrib_and_tests(
    monkeypatch: Any, tmp_path: Path
) -> None:
    fns = _fns(monkeypatch, tmp_path)
    result = asyncio.run(fns["code_security_scan"]())

    assert result["target"] == {"module": None, "path": None}
    files = {row["file"] for row in result["findings"]}
    assert result["files_scanned"] == 2  # vulnmod + Foo.php; contrib/tests pruned
    assert not any("contrib" in f for f in files)
    assert not any("tests/" in f for f in files)


def test_scan_explicit_contrib_module_is_allowed(
    monkeypatch: Any, tmp_path: Path
) -> None:
    fns = _fns(monkeypatch, tmp_path)
    result = asyncio.run(fns["code_security_scan"](module="fine"))
    assert result["files_scanned"] == 1
    assert _pairs(result) == {("xss", "unescaped_print")}


def test_scan_skips_symlinks_out_of_the_docroot(
    monkeypatch: Any, tmp_path: Path
) -> None:
    fns = _fns(monkeypatch, tmp_path)
    root = tmp_path / "root"
    outside = tmp_path / "outside.php"
    outside.write_text("<?php\nprint $leak;\n", encoding="utf-8")
    vulnmod = root / "modules" / "custom" / "vulnmod"
    (vulnmod / "evil.php").symlink_to(outside)

    result = asyncio.run(fns["code_security_scan"](module="vulnmod"))
    files = {row["file"] for row in result["findings"]}
    assert result["files_scanned"] == 2
    assert not any("evil.php" in f for f in files)


def test_scan_filters_by_category_and_severity(monkeypatch: Any, tmp_path: Path) -> None:
    fns = _fns(monkeypatch, tmp_path)

    sql_only = asyncio.run(fns["code_security_scan"](module="vulnmod", categories=["sql_injection"]))
    assert {row["category"] for row in sql_only["findings"]} == {"sql_injection"}
    assert sql_only["counts"]["by_category"] == {"sql_injection": 2}
    assert sql_only["counts"]["by_severity"] == {"high": 2}

    highs = asyncio.run(fns["code_security_scan"](module="vulnmod", severity="high"))
    assert highs["counts"]["by_severity"] == {"high": 7}
    assert all(row["severity"] == "high" for row in highs["findings"])

    mediums = asyncio.run(fns["code_security_scan"](module="vulnmod", severity="medium"))
    assert mediums["counts"]["by_severity"] == {"medium": 3}
    assert {row["pattern"] for row in mediums["findings"]} == {"drupal7_functions"}


def test_scan_truncates_findings_but_not_counts(monkeypatch: Any, tmp_path: Path) -> None:
    fns = _fns(monkeypatch, tmp_path)
    result = asyncio.run(fns["code_security_scan"](module="vulnmod", max_findings=2))
    assert len(result["findings"]) == 2
    assert result["truncated"] is True
    assert result["max_findings"] == 2
    # Counts cover the whole run, not the shown slice.
    assert result["counts"]["by_severity"] == {"high": 7, "medium": 3}
    assert "10 findings total" in result["note"]


def test_scan_rejects_bad_inputs(monkeypatch: Any, tmp_path: Path) -> None:
    fns = _fns(monkeypatch, tmp_path)
    assert "error" in asyncio.run(fns["code_security_scan"](module="vulnmod", path="modules"))
    assert "error" in asyncio.run(fns["code_security_scan"](module="bad-name"))
    assert "Unknown categories" in asyncio.run(
        fns["code_security_scan"](categories=["nope"])
    )["error"]
    assert "available" in asyncio.run(fns["code_security_scan"](categories=["nope"]))
    assert "error" in asyncio.run(fns["code_security_scan"](categories=[]))
    assert "error" in asyncio.run(fns["code_security_scan"](severity="critical"))
    assert "error" in asyncio.run(fns["code_security_scan"](max_findings=0))
    assert "error" in asyncio.run(fns["code_security_scan"](max_findings=600))
    assert "not found" in asyncio.run(fns["code_security_scan"](module="missing_mod"))["error"]
    assert "DRUPAL_ROOT" in asyncio.run(fns["code_security_scan"](path="../etc"))["error"]


def test_scan_requires_a_local_docroot(monkeypatch: Any, tmp_path: Path) -> None:
    fns = _fns(monkeypatch, tmp_path)
    monkeypatch.setattr(security_audit, "get_settings", lambda: _Settings(None))
    assert "DRUPAL_ROOT" in asyncio.run(fns["code_security_scan"](module="vulnmod"))["error"]
    assert "DRUPAL_ROOT" in asyncio.run(fns["route_access_audit"](module="vulnmod"))["error"]


# --- route_access_audit ----------------------------------------------------

def test_scan_treats_js_template_literals_as_not_shell(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """Live-caught: node.preview.js's backticks are template literals."""
    fns = _fns(monkeypatch, tmp_path)
    root = tmp_path / "root"
    vulnmod = root / "modules" / "custom" / "vulnmod"
    (vulnmod / "preview.js").write_text(
        "const html = `<div>${config.label}</div>`;\n", encoding="utf-8"
    )
    result = asyncio.run(fns["code_security_scan"](module="vulnmod"))
    assert not any(row["file"].endswith("preview.js") for row in result["findings"])
    assert result["false_positives_filtered"] == 4  # the 3 + the backtick line
    # The XSS half of the JS registry stays live: innerHTML is still caught.
    (vulnmod / "widget.js").write_text(
        "el.innerHTML = userInput;\n", encoding="utf-8"
    )
    js_scan = asyncio.run(fns["code_security_scan"](module="vulnmod"))
    assert {
        (row["category"], row["pattern"]) for row in js_scan["findings"]
    } >= {("xss", "javascript_innerhtml")}


def test_scan_tolerates_drupal_table_concat_not_user_data(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """Live-caught: core's placeholder queries concat table names, not data."""
    fns = _fns(monkeypatch, tmp_path)
    root = tmp_path / "root"
    vulnmod = root / "modules" / "custom" / "vulnmod"
    (vulnmod / "Storage.php").write_text(
        "<?php\n"
        "class Storage {\n"
        "  public function count() {\n"
        "    return $this->database->query("
        "'SELECT COUNT(*) FROM {' . $this->getRevisionDataTable() . '} "
        "WHERE [nid] = :nid', []);\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    # The dangerous shape — user data concatenated into SQL — must survive
    # the same rule when superglobals are involved.
    (vulnmod / "Loose.php").write_text(
        "<?php\n"
        "return db_query('SELECT * FROM {' . $_GET['t'] . '} WHERE a = :a');\n",
        encoding="utf-8",
    )
    result = asyncio.run(fns["code_security_scan"](module="vulnmod"))
    files = {row["file"] for row in result["findings"]}
    assert not any(f.endswith("Storage.php") for f in files)
    assert any(f.endswith("Loose.php") for f in files)
    assert result["false_positives_filtered"] == 5  # 3 baseline + 2 table rows


def test_scan_distinguishes_no_files_from_no_findings(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """An empty target must not read as a clean bill of health."""
    fns = _fns(monkeypatch, tmp_path)
    root = tmp_path / "root"
    empty = root / "modules" / "custom" / "emptymod"
    empty.mkdir()
    (empty / "empty.routing.yml").write_text("empty.route:\n  path: '/empty'\n", encoding="utf-8")
    result = asyncio.run(fns["code_security_scan"](module="emptymod"))
    assert result["files_scanned"] == 0
    assert result["findings"] == []
    assert "nothing was verified" in result["note"]


def test_route_audit_classifies_every_access_kind(monkeypatch: Any, tmp_path: Path) -> None:
    fns = _fns(monkeypatch, tmp_path)
    result = asyncio.run(fns["route_access_audit"](module="vulnmod"))

    assert result["routing_files"] == 1
    assert [row["name"] for row in result["routes"]] == [
        "vulnmod.admin",
        "vulnmod.custom",
        "vulnmod.entity_form",
        "vulnmod.legacy",
        "vulnmod.open",
        "vulnmod.public",
    ]
    by_name = {row["name"]: row for row in result["routes"]}
    assert by_name["vulnmod.public"]["access"] == "anonymous"
    assert by_name["vulnmod.admin"]["access"] == "permission:administer vulnmod"
    assert by_name["vulnmod.custom"]["access"] == "custom"
    assert by_name["vulnmod.open"]["access"] == "missing"  # reported, not assumed safe

    # An unrecognized underscore requirement is still an access
    # requirement — not "missing" (live: _entity_delete_multiple_access).
    entity_form = by_name["vulnmod.entity_form"]
    assert entity_form["access"] == "requirement:_vulnmod_entity_create"
    assert entity_form["entity_form"] == "vulnmod.add"
    # An alias-only entry inherits its definition elsewhere (often a PHP
    # route provider) — its access cannot be judged from YAML.
    assert by_name["vulnmod.legacy"]["access"] == "alias:vulnmod.public"
    assert by_name["vulnmod.legacy"]["route"] is None

    assert result["counts"] == {
        "permission": 1,
        "custom": 1,
        "missing": 1,
        "anonymous": 1,
        "requirement": 1,
        "alias": 1,
    }
    assert result["anonymous_routes"] == ["vulnmod.public"]
    assert result["routes_missing_access"] == ["vulnmod.open"]
    assert result["alias_routes"] == ["vulnmod.legacy"]

    # The controller resolves to the file declaring the class.
    assert by_name["vulnmod.public"]["controller"] == "\\Drupal\\vulnmod\\Controller\\Foo::page"
    assert by_name["vulnmod.public"]["controller_file"] == (
        "modules/custom/vulnmod/src/Controller/Foo.php"
    )
    assert by_name["vulnmod.open"]["controller_file"] == (
        "modules/custom/vulnmod/src/Controller/Foo.php"
    )
    # CustomForm lives nowhere in the fixture: unknown stays None.
    assert by_name["vulnmod.custom"]["controller_file"] is None

    assert "access: TRUE" in result["note"]
    assert "no access requirement" in result["note"]
    assert "alias:NAME" in result["note"]


def test_route_audit_respects_the_prune_and_target_rules(
    monkeypatch: Any, tmp_path: Path
) -> None:
    fns = _fns(monkeypatch, tmp_path)
    # Default target still finds the module's routing file.
    default = asyncio.run(fns["route_access_audit"]())
    assert default["routing_files"] == 1
    assert len(default["routes"]) == 6

    missing = asyncio.run(fns["route_access_audit"](module="missing_mod"))
    assert "not found" in missing["error"]
    both = asyncio.run(fns["route_access_audit"](module="vulnmod", path="modules"))
    assert "not both" in both["error"]
    escape = asyncio.run(fns["route_access_audit"](path="/etc"))
    assert "DRUPAL_ROOT" in escape["error"]


def test_route_audit_handles_modules_without_routing(monkeypatch: Any, tmp_path: Path) -> None:
    fns = _fns(monkeypatch, tmp_path)
    result = asyncio.run(fns["route_access_audit"](module="fine"))
    assert result["routes"] == []
    assert "No *.routing.yml" in result["note"]
