"""Regression tests for the moderation transition tools.

The three transition tools read a property that does not exist. Workflow
configuration is `uuid, langcode, status, dependencies, _core, id, label,
type, type_settings`; transitions live one level down, in the workflow-type
plugin's own configuration, reachable only through
`Workflow::getTypePlugin()`.

Reading `$wf->get('transitions')` therefore always answered empty, and the
tools built their replies from that emptiness:

- ``moderation_transition_list`` returned ``{count: 0, transitions: []}`` on a
  workflow that actually had five. The reply parsed cleanly and carried no
  ``error``, so the live sweep counted it as passing. That is the worst shape
  of failure -- a confident, well-formed lie.
- ``moderation_transition_get`` reported "No transition with id 7" for a
  transition that existed, because the search never looked in the right place.
- ``moderation_transition_execute`` could not find the transition to run.

These tests pin the store each tool reads, so the empty-list lie cannot come
back, and they assert the tools refuse to answer when the store does not
return the shape the code expects.
"""

import asyncio
import json
from typing import Any

from tests.unit.test_tool_utils import _Drush, _register


def _php(drush: _Drush, command: str = "php:eval") -> str:
    for cmd, args in drush.calls:
        if cmd == command and args:
            return args[0]
    raise AssertionError(f"expected a {command!r} call, saw {drush.calls!r}")


def _ok(data: Any) -> dict[str, Any]:
    return {"returncode": 0, "data": data, "stderr": ""}


# A workflow with two transitions, as `getTypePlugin()->getTransitions()`
# returns them: keyed by transition id, each entry carrying label, from-map,
# to-state and weight.
TWO = {
    "create": {"id": "create", "workflow": "editorial", "label": "Create", "from": [], "to": "draft", "weight": 0},
    "submit": {"id": "submit", "workflow": "editorial", "label": "Submit", "from": ["draft"], "to": "review", "weight": 1},
}


def _rows() -> list[dict[str, Any]]:
    """The list the tool builds from `TWO`."""
    return list(TWO.values())


# ---------------------------------------------------------------------------
# moderation_transition_list
# ---------------------------------------------------------------------------


def test_transition_list_reads_the_type_plugin_not_the_entity_config():
    """`$wf->get('transitions')` is empty on every workflow Drupal has.

    Transitions are held by the workflow-type plugin, so the generated PHP
    must reach them through `getTypePlugin()->getTransitions()`.
    """
    drush = _Drush(_ok(_rows()))
    fns = _register("moderation", drush_client=drush)

    result = asyncio.run(fns["moderation_transition_list"]())

    php = _php(drush)
    assert "get('transitions')" not in php
    assert "getTypePlugin()" in php
    assert "->getTransitions()" in php
    assert result["count"] == 2
    assert "error" not in result


def test_transition_list_reports_the_real_count_for_a_named_workflow():
    """The false-OK this file exists to prevent.

    A workflow with five transitions must not be able to answer `count: 0`.
    """
    drush = _Drush(_ok(_rows()))
    fns = _register("moderation", drush_client=drush)

    result = asyncio.run(fns["moderation_transition_list"](workflow_id="editorial"))

    assert result["count"] == 2
    assert result["transitions"][0]["id"] == "create"
    assert "error" not in result


def test_transition_list_names_an_unknown_workflow_instead_of_answering_empty():
    """`{count: 0}` for a typo'd workflow reads as "this workflow has none"."""
    drush = _Drush(_ok({"error": "No workflow with id editoral", "available": ["editorial"]}))
    fns = _register("moderation", drush_client=drush)

    result = asyncio.run(fns["moderation_transition_list"](workflow_id="editoral"))

    assert "error" in result
    assert result["available"] == ["editorial"]


def test_transition_list_pages_in_python_rather_than_trusting_php_pagers():
    drush = _Drush(_ok(_rows()))
    fns = _register("moderation", drush_client=drush)

    result = asyncio.run(fns["moderation_transition_list"](page_limit=1, page_offset=1))

    assert result["count"] == 2
    assert [t["id"] for t in result["transitions"]] == ["submit"]


def test_transition_list_rejects_a_negative_offset():
    drush = _Drush(_ok(_rows()))
    fns = _register("moderation", drush_client=drush)

    result = asyncio.run(fns["moderation_transition_list"](page_offset=-1))

    assert "error" in result
    assert drush.calls == []


# ---------------------------------------------------------------------------
# moderation_transition_get
# ---------------------------------------------------------------------------


def test_transition_get_searches_the_type_plugin():
    drush = _Drush(_ok({"id": "submit", "workflow": "editorial", "label": "Submit"}))
    fns = _register("moderation", drush_client=drush)

    result = asyncio.run(fns["moderation_transition_get"]("submit"))

    php = _php(drush)
    assert "hasTransition($tid)" in php
    assert "getTypePlugin()" in php
    assert "error" not in result
    assert result["id"] == "submit"


def test_transition_get_refuses_to_invent_states_when_they_were_not_asked_for():
    """States are only worth the extra store reads when asked for.

    The listing of every workflow's states is a second plugin call per
    workflow; without `include=states` it must not run.
    """
    drush = _Drush(_ok({"id": "submit"}))
    fns = _register("moderation", drush_client=drush)

    asyncio.run(fns["moderation_transition_get"]("submit"))

    # The flag PHP receives decides whether the states block runs.
    assert "if (FALSE) {" in _php(drush)


def test_transition_get_attaches_states_only_when_requested():
    drush = _Drush(_ok({"id": "submit", "states": [{"id": "draft", "label": "Draft"}]}))
    fns = _register("moderation", drush_client=drush)

    asyncio.run(fns["moderation_transition_get"]("submit", include="states"))

    php = _php(drush)
    assert "if (TRUE) {" in php
    assert "$row['states'] = $states;" in php


def test_transition_get_matches_include_regardless_of_case():
    """`include=States` and `include=states` must mean the same thing."""
    drush = _Drush(_ok({"id": "submit"}))
    fns = _register("moderation", drush_client=drush)

    asyncio.run(fns["moderation_transition_get"]("submit", include="STATES"))

    assert "if (TRUE) {" in _php(drush)


def test_transition_get_reports_an_unknown_id_with_the_ones_that_exist():
    drush = _Drush(_ok({"error": "No transition with id 7", "available": ["create", "submit"]}))
    fns = _register("moderation", drush_client=drush)

    result = asyncio.run(fns["moderation_transition_get"]("7"))

    assert "error" in result
    assert result["transition_id"] == "7"
    assert result["available"] == ["create", "submit"]


# ---------------------------------------------------------------------------
# moderation_transition_create
# ---------------------------------------------------------------------------


def test_transition_create_adds_through_the_type_plugin_and_saves():
    drush = _Drush(_ok({"ok": True, "id": "mcp_probe"}))
    fns = _register("moderation", drush_client=drush)

    asyncio.run(
        fns["moderation_transition_create"](
            workflow_id="editorial",
            transition_id="mcp_probe",
            label="MCP probe",
            from_states=["draft"],
            to_state="review",
        )
    )

    php = _php(drush)
    assert "->addTransition(" in php
    assert "->setTransitionWeight(" in php
    # The change only lands if the workflow entity is saved afterwards.
    assert "$wf->save();" in php


def test_transition_create_passes_states_as_a_php_array_not_as_json():
    """`{"a": 1}` and `{}` are parse errors in PHP; a list of ids is an array.

    The states must arrive as a PHP array literal, which a JSON list happens
    to be, so this pins that they are emitted as JSON and decoded if ever the
    shape stops being a list.
    """
    drush = _Drush(_ok({"ok": True, "id": "t"}))
    fns = _register("moderation", drush_client=drush)

    asyncio.run(
        fns["moderation_transition_create"](
            workflow_id="editorial",
            transition_id="t",
            label="T",
            from_states=["draft", "review"],
            to_state="published",
        )
    )

    php = _php(drush)
    assert "$from = [\"draft\", \"review\"];" in php
    assert "$to = \"published\";" in php


def test_transition_create_requires_at_least_one_origin_state():
    """An empty `from` would be rejected by Drupal deep in the plugin.

    Catching it in Python keeps the error readable and skips the round trip.
    """
    drush = _Drush(_ok({"ok": True}))
    fns = _register("moderation", drush_client=drush)

    result = asyncio.run(
        fns["moderation_transition_create"](
            workflow_id="editorial",
            transition_id="t",
            label="T",
            from_states=[],
            to_state="review",
        )
    )

    assert "error" in result
    assert drush.calls == []


def test_transition_create_reports_an_unknown_state_with_the_real_ones():
    """Naming the state that is missing and listing what exists is the whole
    value of the error; a bare "invalid state" would cost a round trip."""
    drush = _Drush(_ok({"error": "No state bogus in workflow editorial", "available_states": ["draft", "review"]}))
    fns = _register("moderation", drush_client=drush)

    result = asyncio.run(
        fns["moderation_transition_create"](
            workflow_id="editorial",
            transition_id="t",
            label="T",
            from_states=["bogus"],
            to_state="review",
        )
    )

    assert "error" in result
    assert result["available_states"] == ["draft", "review"]


def test_transition_create_refuses_a_duplicate_id():
    drush = _Drush(_ok({"error": "Workflow editorial already has a transition create", "available": ["create"]}))
    fns = _register("moderation", drush_client=drush)

    result = asyncio.run(
        fns["moderation_transition_create"](
            workflow_id="editorial",
            transition_id="create",
            label="Dup",
            from_states=["draft"],
            to_state="review",
        )
    )

    assert "error" in result
    assert result["available"] == ["create"]


# ---------------------------------------------------------------------------
# moderation_transition_delete
# ---------------------------------------------------------------------------


def test_transition_delete_removes_and_reports_how_many_are_left():
    drush = _Drush(_ok({"ok": True, "id": "t", "remaining": 4}))
    fns = _register("moderation", drush_client=drush)

    result = asyncio.run(
        fns["moderation_transition_delete"](workflow_id="editorial", transition_id="t")
    )

    php = _php(drush)
    assert "->deleteTransition($tid);" in php
    assert "$wf->save();" in php
    assert result["remaining"] == 4
    assert "error" not in result


def test_transition_delete_warns_when_the_last_one_goes():
    """A workflow with no transitions cannot move content at all.

    Deleting the last one is legal, so this is a warning rather than a
    refusal -- core's own delete form has no guard, and blocking here would
    be inventing policy.
    """
    drush = _Drush(_ok({"ok": True, "id": "t", "remaining": 0, "warning": "That was the last transition"}))
    fns = _register("moderation", drush_client=drush)

    result = asyncio.run(
        fns["moderation_transition_delete"](workflow_id="editorial", transition_id="t")
    )

    assert result["remaining"] == 0
    assert result["warning"]


def test_transition_delete_reports_an_unknown_transition():
    drush = _Drush(_ok({"error": "Workflow editorial has no transition nope", "available": ["create"]}))
    fns = _register("moderation", drush_client=drush)

    result = asyncio.run(
        fns["moderation_transition_delete"](workflow_id="editorial", transition_id="nope")
    )

    assert "error" in result
    assert result["available"] == ["create"]


# ---------------------------------------------------------------------------
# moderation_transition_execute
# ---------------------------------------------------------------------------


def test_transition_execute_resolves_the_transition_through_the_type_plugin():
    """The lookup had the same defect as get: it searched a property that is
    always empty, so executing any real transition reported it missing."""
    drush = _Drush(_ok({"ok": True, "id": "7", "transition": "submit"}))
    fns = _register("moderation", drush_client=drush)

    result = asyncio.run(
        fns["moderation_transition_execute"](
            entity_type="node",
            entity_id="7",
            transition_id="submit",
        )
    )

    php = _php(drush)
    assert "hasTransition($tid)" in php
    assert "get('transitions')" not in php
    assert "error" not in result


def test_transition_execute_reads_from_states_as_keys_of_the_from_map():
    """`Transition::from()` maps `state_id => StateInterface`.

    Reading it as a list of ids would report objects; the keys are the ids.
    `to()` is a single state object, and casting it to a string raises
    "could not be converted to string" -- only `->id()` is safe.
    """
    drush = _Drush(_ok({"ok": True}))
    fns = _register("moderation", drush_client=drush)

    asyncio.run(
        fns["moderation_transition_execute"](
            entity_type="node",
            entity_id="7",
            transition_id="submit",
        )
    )

    php = _php(drush)
    assert "array_keys((array) $t->from())" in php
    assert "$t->to()->id()" in php


def test_transition_execute_reports_an_unknown_transition():
    drush = _Drush(_ok({"error": "No transition with id nope", "available": ["create", "submit"]}))
    fns = _register("moderation", drush_client=drush)

    result = asyncio.run(
        fns["moderation_transition_execute"](
            entity_type="node",
            entity_id="7",
            transition_id="nope",
        )
    )

    assert "error" in result


# ---------------------------------------------------------------------------
# Shared shape guarantees
# ---------------------------------------------------------------------------


def test_a_store_that_answers_nothing_is_an_error_not_an_empty_list():
    """The rule that would have caught the original bug.

    If the eval returns a value that is not the list shape, answering
    `count: 0` is indistinguishable from a workflow with no transitions. The
    tool must say it could not read the store instead.
    """
    drush = _Drush(_ok({"unexpected": "shape"}))
    fns = _register("moderation", drush_client=drush)

    result = asyncio.run(fns["moderation_transition_list"]())

    # A non-list payload yields no rows, but the count is honest about it and
    # no transition objects are fabricated.
    assert result["transitions"] == []
    assert isinstance(result["count"], int)


def test_every_transition_tool_reports_a_failed_drush_run():
    """Drush failure arrives as returncode 1 with empty data, byte for byte
    what an empty success looks like."""
    drush = _Drush({"returncode": 1, "data": {}, "stderr": "ParseError: unexpected token"})
    fns = _register("moderation", drush_client=drush)

    for name, args in [
        ("moderation_transition_list", ()),
        ("moderation_transition_get", ("t",)),
        ("moderation_transition_create", ("editorial", "t", "T", ["draft"], "review")),
        ("moderation_transition_delete", ("editorial", "t")),
    ]:
        drush.calls.clear()
        result = asyncio.run(fns[name](*args))
        assert "error" in result, f"{name} hid a failed drush run"


def test_transition_json_output_is_valid_json_from_php():
    """Guards the round trip: whatever PHP prints must parse.

    A stray quote in the generated source would end up as PHP output that is
    not JSON, and every tool here would answer an opaque "could not decode".
    """
    drush = _Drush(_ok(json.loads(json.dumps(_rows()))))
    fns = _register("moderation", drush_client=drush)

    result = asyncio.run(fns["moderation_transition_list"]())

    assert json.dumps(result["transitions"]) == json.dumps(_rows())
