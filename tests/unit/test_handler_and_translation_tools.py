"""Regression tests for webform handlers, interface translations and transitions.

Each test pins the specific shape that was wrong, so none can return silently.

Three classes of bug are covered here:

1. **Tool shapes that lied.** A tool that returned ``{count: 0}`` on a
   workflow that actually has five transitions was counted as passing by the
   live sweep, because the reply parsed and carried no ``error``. The fix is
   to refuse to answer when the underlying store does not return the shape
   the code expects, so every one of these tests asserts on the refusal as
   well as on the happy path.
2. **PHP that only a live site can reject.** ``json.dumps`` is not a PHP
   literal: ``{}`` is a parse error there, and a French label arrives as the
   six literal characters ``\\u00e9``. Tests assert the emitted PHP uses
   base64 or scalar literals rather than JSON, so a non-ASCII value cannot
   regress into silent mangling.
3. **Drupal APIs that answer by throwing.** ``Webform::getHandler()`` throws
   ``PluginNotFoundException`` for an id it has never seen instead of
   returning ``NULL``, so "is there a handler called X?" explodes rather than
   answering no. Tests assert the generated PHP asks the plugin collection's
   own id list instead.
"""

import asyncio
import base64
import json
from typing import Any

from tests.unit.test_tool_utils import _Drush, _register


def _php(drush: _Drush, command: str = "php:eval") -> str:
    """Return the PHP handed to ``drush <command>``."""
    for cmd, args in drush.calls:
        if cmd == command and args:
            return args[0]
    raise AssertionError(f"expected a {command!r} call, saw {drush.calls!r}")


def _ok(data: Any) -> dict[str, Any]:
    return {"returncode": 0, "data": data, "stderr": ""}


def _decode_php_text(php: str, name: str) -> str:
    """Recover the value of a ``$name = base64_decode('...');`` assignment."""
    prefix = f"${name} = base64_decode('"
    start = php.index(prefix) + len(prefix)
    end = php.index("');", start)
    return base64.b64decode(php[start:end]).decode("utf-8")


# ---------------------------------------------------------------------------
# php_text / php_json
# ---------------------------------------------------------------------------


def test_php_text_hands_non_ascii_over_as_base64_not_as_json_escapes():
    """PHP has no `\\uXXXX` escape; JSON's escapes are not PHP's escapes.

    Dropping a French label into PHP source as ``json.dumps`` would produce
    the literal six characters ``\\u00e9``, and any ``$`` in the text would
    start a variable interpolation that eats the rest of the word. Base64
    makes the value inert to PHP, the shell and Drush alike.
    """
    from drupal_mcp_server.tools._utils import php_text

    php = php_text('Café $total \\ "quoted"')

    assert php.startswith("base64_decode('")
    assert "u00e9" not in php
    # The whole value is inside one base64 literal, so `$` cannot interpolate.
    assert "$" not in php
    assert base64.b64decode(php.split("'")[1]).decode() == 'Café $total \\ "quoted"'


def test_php_json_decodes_to_a_php_array_because_a_json_object_is_not_one():
    """`{}` and `{"k": 1}` are both parse errors in PHP source.

    Any dict embedded into `php:eval` must therefore travel as a JSON string
    that PHP decodes, never as a PHP array literal.
    """
    from drupal_mcp_server.tools._utils import php_json

    php = php_json({"to_mail": "a@b.test"})

    assert php.startswith("json_decode(base64_decode('")
    assert php.endswith("), TRUE)")
    payload = json.loads(base64.b64decode(php.split("'")[1]).decode())
    assert payload == {"to_mail": "a@b.test"}


def test_php_json_keeps_none_as_null_rather_than_the_string_none():
    from drupal_mcp_server.tools._utils import php_json

    php = php_json(None)

    assert base64.b64decode(php.split("'")[1]).decode() == "null"


# ---------------------------------------------------------------------------
# interface_translation_*
# ---------------------------------------------------------------------------


def test_interface_translation_list_refuses_filters_it_cannot_apply():
    """An unknown filter must not be silently dropped.

    The old tool forwarded whatever it was given; a typo'd key produced a
    listing that ignored the filter and looked like a real answer.
    """
    drush = _Drush(_ok({"translations": []}))
    fns = _register("multilingual", drush_client=drush)

    result = asyncio.run(
        fns["interface_translation_list"](langcode="fr", filters={"langugage": "fr"})
    )

    assert "error" in result
    assert "langugage" in result["error"]
    assert drush.calls == []


def test_interface_translation_list_embeds_filters_as_scalars_not_as_json():
    """An empty filters dict used to be interpolated as `{}`.

    That is a PHP parse error, so the tool died with a ParseError rather than
    returning an empty page. Filters are now pulled apart in Python and handed
    over as scalars.
    """
    drush = _Drush(_ok({"translations": [], "count": 0}))
    fns = _register("multilingual", drush_client=drush)

    result = asyncio.run(
        fns["interface_translation_list"](langcode="fr", filters={}, page_limit=5)
    )

    php = _php(drush)
    assert "= {};" not in php
    assert "$search = base64_decode('');" in php
    assert "$ctx = NULL;" in php
    assert "$limit = 5;" in php
    assert "error" not in result


def test_interface_translation_list_passes_a_context_filter_through():
    drush = _Drush(_ok({"translations": [], "count": 0}))
    fns = _register("multilingual", drush_client=drush)

    asyncio.run(
        fns["interface_translation_list"](
            langcode="fr", filters={"context": "menu", "search": "Save"}
        )
    )

    php = _php(drush)
    assert _decode_php_text(php, "ctx") == "menu"
    assert _decode_php_text(php, "search") == "Save"


def test_interface_translation_list_reports_a_store_it_cannot_parse():
    """Refusing beats inventing an empty page.

    If locale stops returning the list shape, `count: 0` would be read as
    "this site has no translations", which is exactly the kind of silent
    false-OK that hid a broken tool for a whole sweep.
    """
    drush = _Drush(_ok({"unexpected": True}))
    fns = _register("multilingual", drush_client=drush)

    result = asyncio.run(fns["interface_translation_list"](langcode="fr"))

    assert "error" in result
    assert "did not return a translation list" in result["error"]


def test_interface_translation_add_refuses_a_source_locale_does_not_know():
    """Locale answers these through the printed JSON, not a non-zero exit.

    `php:eval` returns 0 either way, so a reply carrying `error` must be
    surfaced rather than treated as success.
    """
    drush = _Drush(_ok({"error": "There is no source string \"Nope\"."}))
    fns = _register("multilingual", drush_client=drush)

    result = asyncio.run(
        fns["interface_translation_add"](
            source="Nope", langcode="fr", translation="x"
        )
    )

    assert "error" in result
    assert "no source string" in result["error"]
    assert result["source"] == "Nope"
    assert result["langcode"] == "fr"


def test_interface_translation_delete_reports_a_missing_translation():
    drush = _Drush(_ok({"error": "There is no de translation for \"Save\".", "lid": 2}))
    fns = _register("multilingual", drush_client=drush)

    result = asyncio.run(
        fns["interface_translation_delete"](source="Save", langcode="de")
    )

    assert "error" in result
    assert result["lid"] == 2


def test_interface_translation_add_passes_user_text_through_php_text():
    """Source, translation and language all travel as base64.

    A source string containing `$` or a non-ASCII character is common on a
    multilingual site; either would corrupt the PHP if interpolated.
    """
    drush = _Drush(_ok({"ok": True, "lid": 7, "created": True}))
    fns = _register("multilingual", drush_client=drush)

    asyncio.run(
        fns["interface_translation_add"](
            source="Preço $total", langcode="fr", translation="Chaîne"
        )
    )

    php = _php(drush)
    assert _decode_php_text(php, "source") == "Preço $total"
    assert _decode_php_text(php, "text") == "Chaîne"
    assert _decode_php_text(php, "lang") == "fr"
    # The write must be followed by the official cache refresh.
    assert "_locale_refresh_translations" in php


# ---------------------------------------------------------------------------
# webform_handler_*
# ---------------------------------------------------------------------------


def test_webform_handler_create_never_asks_webform_for_an_unknown_handler():
    """`Webform::getHandler()` throws rather than returning NULL.

    Asked "does contact have a handler called x?" it reaches the plugin
    collection's `initializePlugin()` with an empty configuration and raises
    `PluginNotFoundException`, so the guard that is supposed to detect a
    duplicate is the thing that kills the tool. The check must read the
    collection's own id list.
    """
    drush = _Drush(_ok({"ok": True, "id": "x"}))
    fns = _register("webform", drush_client=drush)

    asyncio.run(
        fns["webform_handler_create"](
            id="x",
            webform_id="contact",
            handler_type="email",
            label="X",
        )
    )

    php = _php(drush)
    assert "$wf->getHandler($hid)" not in php
    assert "getHandlers()->getInstanceIds()" in php
    assert "in_array($hid" in php


def test_webform_handler_locate_never_asks_webform_for_an_unknown_handler():
    """The same trap on the update/delete lookup path.

    The search across every webform must ask the collection for its id list;
    calling `getHandler()` on a candidate that does not own the id throws
    before the loop can finish, so the "no webform has a handler" error would
    never be reached.
    """
    drush = _Drush(_ok({"ok": True, "id": "email_confirmation"}))
    fns = _register("webform", drush_client=drush)

    asyncio.run(fns["webform_handler_update"]("email_confirmation", label="New"))

    php = _php(drush)
    # The only two calls are the confirmed-match lookups, one per branch; both
    # are reached after the id list has already proved the handler exists.
    assert php.count("$handler = $wf->getHandler($hid);") == 2
    assert php.count("getInstanceIds()") >= 1
    assert "in_array($hid, $candidate->getHandlers()->getInstanceIds(), TRUE)" in php


def test_webform_handler_update_reports_an_ambiguous_id_instead_of_guessing():
    """A handler id is unique within one webform, not site-wide.

    Without `webform_id` the tool searches; several matches must be reported
    with the candidates rather than silently editing the first.
    """
    drush = _Drush(_ok({"error": "Handler id h is used by 2 webforms: a, b.", "matches": ["a", "b"]}))
    fns = _register("webform", drush_client=drush)

    result = asyncio.run(fns["webform_handler_update"]("h", label="L"))

    assert "error" in result
    assert result["matches"] == ["a", "b"]


def test_webform_handler_update_refuses_when_there_is_nothing_to_change():
    """Calling update with no fields would be a no-op write.

    It still costs a save and a cache clear, and the reply would read as a
    successful edit that changed nothing.
    """
    drush = _Drush(_ok({"ok": True}))
    fns = _register("webform", drush_client=drush)

    result = asyncio.run(fns["webform_handler_update"]("h"))

    assert "error" in result
    assert drush.calls == []


def test_webform_handler_update_replaces_named_settings_and_keeps_the_rest():
    """Partial configuration must not wipe the plugin's other settings.

    `Webform::updateWebformHandler()` writes the whole handler configuration,
    so passing only the keys you want to change has to be merged over what is
    already there.
    """
    drush = _Drush(_ok({"ok": True, "id": "h", "handler": {}}))
    fns = _register("webform", drush_client=drush)

    asyncio.run(fns["webform_handler_update"]("h", configuration={"to_mail": "a@b.test"}))

    php = _php(drush)
    assert "array_replace($cfg['settings']" in php
    assert "json_decode(base64_decode('" in php


def test_webform_handler_delete_returns_the_handler_id_it_actually_deleted():
    """The reply used to name an undefined PHP variable, so it read "".

    `$handler_id` never existed in the generated code; PHP treats the
    undefined variable as an empty string and the tool reports a blank id for
    a delete that did happen.
    """
    drush = _Drush(_ok({"ok": True, "id": "", "deleted": True, "remaining": 2}))
    fns = _register("webform", drush_client=drush)

    asyncio.run(fns["webform_handler_delete"]("h", webform_id="contact"))

    php = _php(drush)
    assert "(string) $hid" in php
    assert "(string) $handler_id" not in php


def test_webform_handler_delete_refuses_to_claim_success_without_a_confirmation():
    """Silence is not a delete.

    If the PHP prints nothing recognisable, reporting `deleted: true` would
    leave the caller believing a handler is gone while it is still attached.
    """
    drush = _Drush(_ok({}))
    fns = _register("webform", drush_client=drush)

    result = asyncio.run(fns["webform_handler_delete"]("h"))

    assert "error" in result
    assert "did not confirm" in result["error"]


def test_webform_handler_create_passes_settings_through_php_json():
    """A JSON object literal is not a PHP array literal.

    Both `{}` and `{"k": 1}` are parse errors, so settings must reach PHP as
    a JSON string that PHP decodes.
    """
    drush = _Drush(_ok({"ok": True, "id": "h"}))
    fns = _register("webform", drush_client=drush)

    asyncio.run(
        fns["webform_handler_create"](
            id="h",
            webform_id="contact",
            handler_type="email",
            label="H",
            configuration={"to_mail": "a@b.test"},
        )
    )

    php = _php(drush)
    assert "json_decode(base64_decode('" in php
    assert "$settings = {};" not in php
