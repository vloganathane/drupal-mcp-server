"""The sweep is the only thing that ever sees all 366 tools.

A bug in how it chooses arguments, or in how it reads an answer back, does not
fail anything -- it quietly mislabels the whole report, and the report is the
deliverable. Two such bugs are pinned here: a `langcode` filled with junk made
create_term answer 403 about a field permission instead of running, and
`ddev_exec` was handed `status`, which is a drush command and not a shell one.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

_LIVE = Path(__file__).resolve().parents[1] / "live" / "sweep.py"


@pytest.fixture(scope="module")
def sweep() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sweep_live", _LIVE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_optional_langcode_is_omitted(sweep: ModuleType) -> None:
    """JSON:API write-protects `langcode` on a multilingual site whatever the
    value, so sending one costs the tool a 403 it did not cause."""
    schema = {
        "properties": {
            "vid": {"type": "string"},
            "name": {"type": "string"},
            "langcode": {"type": "string", "default": None},
        },
        "required": ["vid", "name"],
    }

    assert sweep.synthesize(schema) == {"vid": "tags", "name": "sweep_name"}


def test_required_langcode_still_gets_a_value(sweep: ModuleType) -> None:
    """A caller who named the argument cannot have it dropped -- that is a
    missing_argument, which the server refuses and the sweep used to count
    as a pass."""
    schema = {
        "properties": {
            "langcode": {"type": "string"},
            "translation": {"type": "object"},
        },
        "required": ["langcode", "translation"],
    }

    assert sweep.synthesize(schema)["langcode"] == "en"


def test_container_tools_get_a_command_the_container_has(sweep: ModuleType) -> None:
    """`ddev_exec` runs its argument inside the container, where `status` --
    the right answer for drush_command -- is not a command at all."""
    schema = {"properties": {"command": {"type": "string"}}}

    assert sweep.synthesize(schema, "ddev_exec")["command"] == "php -v"
    assert sweep.synthesize(schema, "lando_exec")["command"] == "php -v"
    assert sweep.synthesize(schema, "drush_command")["command"] == "status"


def test_queue_run_uses_a_queue_that_exists(sweep: ModuleType) -> None:
    schema = {"properties": {"queue_name": {"type": "string"}}}
    sweep.EXISTING_QUEUE = "real_queue"
    try:
        assert sweep.synthesize(schema, "queue_run")["queue_name"] == "real_queue"
    finally:
        sweep.EXISTING_QUEUE = ""

    # With nothing found, the name falls through rather than being blank: a
    # queue that is not there is an honest answer to report.
    schema_default = {"properties": {"queue_name": {"type": "string"}}}
    assert sweep.synthesize(schema_default, "queue_run")["queue_name"] == "sweep_name"


def test_a_failed_drush_run_is_not_counted_ok(sweep: ModuleType) -> None:
    """A Drush failure carries no `error` key, so the fall-through used to
    read `data: {}` as an empty success for db_query, db_tables and every
    `ev` tool."""
    verdict, detail = sweep.classify(
        {"returncode": 1, "stderr": "Could not connect to database"},
        "db_query",
        False,
    )

    assert verdict == "REJECTED"
    assert "Could not connect" in detail


def test_a_broken_tool_is_still_dead(sweep: ModuleType) -> None:
    """Reaching Drupal is what the change above protects; a tool that fails
    the same way on every call is still DEAD rather than merely rejected."""
    verdict, _ = sweep.classify(
        {"returncode": 1, "stderr": "Too many arguments"}, "db_tables", False
    )

    assert verdict == "DEAD"


def test_a_passing_run_stays_ok(sweep: ModuleType) -> None:
    assert sweep.classify({"data": {"rows": [1]}, "returncode": 0}, "db_query", False) == (
        "OK",
        "",
    )
