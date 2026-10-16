"""Unit tests for the site status, update, and health tools.

These tools exist because the questions an agent asks first -- what is
wrong, what needs updating, can this server reach the site -- used to be
opaque connection errors. The drush and composer surfaces are faked here
against the exact shapes the live commands return, captured from
Drupal 11.4 with Drush 13.
"""

from typing import Any

import drupal_mcp_server.tools.status as status


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
    status.register_tools(mcp, **deps)
    return mcp.fns


class _Drush:
    """Answers each command with a canned result."""

    def __init__(self, results: dict[str, Any]) -> None:
        self.results = results
        self.calls: list[tuple[str, list[str]]] = []

    async def run(self, command: str, args: list[str] | None = None, **kwargs: Any):
        self.calls.append((command, list(args or [])))
        return self.results.get(command, {"returncode": 0, "data": {}})


_REQUIREMENTS = {
    "cron": {
        "title": "Cron maintenance task",
        "severity": "Error",
        "description": "Last run 3 days ago.",
        "value": "3 days",
    },
    "php": {
        "title": "PHP",
        "severity": "Warning",
        "description": "PHP is 8.1, supported is 8.3.",
        "value": "8.1",
    },
    "update": {
        "title": "Used database migrations",
        "severity": "OK",
        "description": "All DB updates applied.",
        "value": 0,
    },
    "oddity": {
        "title": "A requirement this tool cannot classify",
        "severity": "Mystery",
        "description": "From a contrib module.",
        "value": "?",
    },
}


def test_status_report_keeps_errors_warnings_and_the_unclassifiable():
    import asyncio

    drush = _Drush({"core:requirements": {"returncode": 0, "data": _REQUIREMENTS}})
    fns = _tool_functions(drush_client=drush)

    result = asyncio.run(fns["status_report"]())

    ids = [row["id"] for row in result["requirements"]]
    # "OK" is hidden by default; the unknown severity is kept, because a
    # level this tool cannot parse is itself worth showing.
    assert ids == ["cron", "php", "oddity"]
    assert result["counts"] == {
        "error": 1,
        "warning": 1,
        "info": 0,
        "ok": 1,
        "unknown": 1,
    }
    assert result["total"] == 4
    assert drush.calls == [("core:requirements", ["--format=json"])]


def test_status_report_include_ok_and_severity_filter():
    import asyncio

    drush = _Drush({"core:requirements": {"returncode": 0, "data": _REQUIREMENTS}})
    fns = _tool_functions(drush_client=drush)

    everything = asyncio.run(fns["status_report"](include_ok=True))
    warnings = asyncio.run(fns["status_report"](severity_filter="warning"))

    assert everything["returned"] == 4
    assert [row["id"] for row in warnings["requirements"]] == ["php"]
    assert warnings["filtered_by"] == "warning"


def test_status_report_rejects_an_unknown_filter_and_reports_site_failures():
    import asyncio

    drush = _Drush(
        {
            "core:requirements": {
                "returncode": 1,
                "data": {},
                "stderr": "The entity does not have an ID.",
            }
        }
    )
    fns = _tool_functions(drush_client=drush)

    bad = asyncio.run(fns["status_report"](severity_filter="fatal"))
    failed = asyncio.run(fns["status_report"]())

    assert "severity_filter must be one of" in bad["error"]
    assert failed["returncode"] == 1
    assert "entity does not have an ID" in failed["error"]
    assert "requirements checker failed" in failed["note"]


def test_database_updates_reads_a_pending_list():
    import asyncio

    pending = [{"module": "node", "description": "Add index", "number": "node_add_index_1"}]
    drush = _Drush({"updatedb:status": {"returncode": 0, "data": pending}})
    fns = _tool_functions(drush_client=drush)

    result = asyncio.run(fns["database_updates"]())

    assert result["pending"] == pending
    assert result["count"] == 1
    assert "drush updatedb" in result["hint"]


def test_database_updates_recognises_a_clean_site():
    """On a clean site drush sends an empty stdout and puts its [success]
    line on stderr -- verified live against Drush 13 -- so the sentence on
    stderr, not any JSON shape, is what says there is nothing to do."""
    import asyncio

    drush = _Drush(
        {
            "updatedb:status": {
                "returncode": 0,
                "data": {},
                "stderr": " [success] No database updates required.\n",
            }
        }
    )
    fns = _tool_functions(drush_client=drush)

    result = asyncio.run(fns["database_updates"]())

    assert result["pending"] == []
    assert result["count"] == 0
    assert "No database updates required" in result["note"]


def test_database_updates_wraps_stdout_text_and_surfaces_unknown_output():
    """Both fallback shapes: unparsed stdout text, and a result with no
    answer anywhere -- which must say so and carry the stderr."""
    import asyncio

    text = _Drush(
        {
            "updatedb:status": {
                "returncode": 0,
                "data": {"output": " [success] No database updates required.\n"},
            }
        }
    )
    blank = _Drush(
        {
            "updatedb:status": {
                "returncode": 0,
                "data": {},
                "stderr": "Warning: something odd happened\n",
            }
        }
    )

    via_text = asyncio.run(_tool_functions(drush_client=text)["database_updates"]())
    via_blank = asyncio.run(_tool_functions(drush_client=blank)["database_updates"]())

    assert via_text["pending"] == []
    assert "No database updates required" in via_text["note"]
    assert via_blank["pending"] == []
    assert via_blank["count"] is None
    assert "something odd" in via_blank["stderr"]


_OUTDATED = {
    "installed": [
        {
            "name": "drupal/core",
            "version": "11.4.9",
            "latest": "11.4.10",
            "latest-status": "semver-safe-update",
            "direct-dependency": True,
            "abandoned": False,
            "description": "Drupal",
        },
        {
            "name": "drupal/token",
            "version": "1.15.0",
            "latest": "1.16.0",
            "latest-status": "semver-safe-update",
            "direct-dependency": True,
            "abandoned": False,
            "description": "Token",
        },
        {
            "name": "psr/log",
            "version": "3.0.0",
            "latest": "3.0.1",
            "latest-status": "semver-safe-update",
            "direct-dependency": False,
            "abandoned": False,
            "description": "PSR-3",
        },
        {
            "name": "phpunit/phpunit",
            "version": "10.5.0",
            "latest": "10.5.40",
            "latest-status": "semver-safe-update",
            "direct-dependency": False,
            "abandoned": False,
            "description": "Testing",
        },
    ]
}

_AUDIT = {
    "advisories": {
        "drupal/token": [
            {
                "title": "XSS bypass",
                "cve": "CVE-2026-0001",
                "affectedVersions": "<1.16.0",
                "link": "https://www.drupal.org/project/token",
            }
        ]
    }
}


class _Composer:
    """Fakes run_composer, keyed by the composer subcommand."""

    def __init__(self, outputs: dict[str, dict[str, Any]]) -> None:
        self.outputs = outputs
        self.calls: list[list[str]] = []

    async def __call__(self, args: list[str], tail: int | None = None) -> dict[str, Any]:
        self.calls.append(list(args))
        return self.outputs[args[0]]


def test_available_updates_groups_packages_and_excludes_dev(monkeypatch):
    import asyncio
    import json

    composer = _Composer(
        {"outdated": {"returncode": 0, "output": json.dumps(_OUTDATED)}}
    )
    monkeypatch.setattr(status, "run_composer", composer, raising=True)
    monkeypatch.setattr(status, "_dev_dependencies", lambda root: {"phpunit/phpunit"})
    fns = _tool_functions(drush_client=None)

    result = asyncio.run(fns["available_updates"]())

    names = [p["name"] for p in result["core"] + result["contrib"] + result["other"]]
    assert "phpunit/phpunit" not in names
    assert result["dev_filtered"] is True
    assert [p["name"] for p in result["core"]] == ["drupal/core"]
    assert [p["name"] for p in result["contrib"]] == ["drupal/token"]
    assert [p["name"] for p in result["other"]] == ["psr/log"]
    assert result["total"] == 3
    assert result["core"][0]["latest_status"] == "semver-safe-update"
    assert composer.calls == [["outdated", "--format=json"]]


def test_available_updates_include_dev_keeps_dev_packages(monkeypatch):
    import asyncio
    import json

    composer = _Composer(
        {"outdated": {"returncode": 0, "output": json.dumps(_OUTDATED)}}
    )
    monkeypatch.setattr(status, "run_composer", composer, raising=True)
    monkeypatch.setattr(status, "_dev_dependencies", lambda root: {"phpunit/phpunit"})
    fns = _tool_functions(drush_client=None)

    result = asyncio.run(fns["available_updates"](include_dev=True))

    names = [p["name"] for p in result["core"] + result["contrib"] + result["other"]]
    assert "phpunit/phpunit" in names
    assert result["dev_filtered"] is False


def test_available_updates_security_only_intersects_the_audit(monkeypatch):
    import asyncio
    import json

    composer = _Composer(
        {
            "outdated": {"returncode": 0, "output": json.dumps(_OUTDATED)},
            "audit": {"returncode": 0, "output": json.dumps(_AUDIT)},
        }
    )
    monkeypatch.setattr(status, "run_composer", composer, raising=True)
    fns = _tool_functions(drush_client=None)

    result = asyncio.run(fns["available_updates"](security_only=True))

    assert result["total"] == 1
    assert result["contrib"][0]["name"] == "drupal/token"
    assert result["contrib"][0]["advisories"][0]["cve"] == "CVE-2026-0001"
    assert composer.calls[1] == ["audit", "--format=json"]


def test_available_updates_keeps_everything_when_the_audit_fails(monkeypatch):
    import asyncio
    import json

    composer = _Composer(
        {
            "outdated": {"returncode": 0, "output": json.dumps(_OUTDATED)},
            "audit": {"returncode": 1, "output": "", "error": "no network"},
        }
    )
    monkeypatch.setattr(status, "run_composer", composer, raising=True)
    fns = _tool_functions(drush_client=None)

    result = asyncio.run(fns["available_updates"](security_only=True))

    assert result["total"] == 4
    assert "did not return advisories" in result["security_note"]


def test_available_updates_reports_composer_failures(monkeypatch):
    import asyncio

    async def broken(args: list[str], tail: int | None = None) -> dict[str, Any]:
        return {
            "returncode": 127,
            "output": "",
            "error": "composer is not on PATH",
            "command": "composer outdated --format=json",
        }

    monkeypatch.setattr(status, "run_composer", broken, raising=True)
    fns = _tool_functions(drush_client=None)

    result = asyncio.run(fns["available_updates"]())

    assert "composer is not on PATH" in result["error"]


class _JSONAPI:
    def __init__(self) -> None:
        self.index = {"data": [{"type": "node"}]}

    async def get_index(self) -> Any:
        return self.index


_STATUS = {
    "drupal-version": "11.4.10",
    "drush-version": "13.6.0",
    "php-version": "8.3.21",
    "db-status": "Connected",
    "bootstrap": "Successful",
}


def test_health_check_passes_on_a_healthy_site():
    import asyncio

    drush = _Drush(
        {
            "status": {"returncode": 0, "data": _STATUS},
            "pm:list": {
                "returncode": 0,
                "data": {"jsonapi": "JSON:API", "dblog": "Database logging", "basic_auth": "Basic Authentication"},
            },
        }
    )
    fns = _tool_functions(drush_client=drush, jsonapi_client=_JSONAPI())

    result = asyncio.run(fns["health_check"]())

    assert result["ok"] is True
    assert result["problems"] == []
    assert result["database"]["ok"] is True
    assert result["modules"]["jsonapi"] is True


def test_health_check_names_each_problem_with_its_fix():
    import asyncio

    drush = _Drush(
        {
            "status": {"returncode": 0, "data": {**_STATUS, "db-status": "Not connected"}},
            "pm:list": {"returncode": 0, "data": {"jsonapi": "JSON:API"}},
        }
    )

    class NoIndex:
        async def get_index(self) -> Any:
            raise RuntimeError("403 Forbidden")

    fns = _tool_functions(drush_client=drush, jsonapi_client=NoIndex())

    result = asyncio.run(fns["health_check"]())

    assert result["ok"] is False
    checks = {p["check"] for p in result["problems"]}
    assert checks == {"database", "jsonapi", "module:dblog", "module:basic_auth"}
    db_problem = next(p for p in result["problems"] if p["check"] == "database")
    assert "ddev start" in db_problem["hint"]
    jsonapi_problem = next(p for p in result["problems"] if p["check"] == "jsonapi")
    assert "drush en jsonapi" in jsonapi_problem["hint"]


def test_health_check_without_a_drush_client_says_how_to_fix_it():
    import asyncio

    fns = _tool_functions(drush_client=None)

    result = asyncio.run(fns["health_check"]())

    assert result["ok"] is False
    assert "DRUSH_PATH" in result["problems"][0]["hint"]
