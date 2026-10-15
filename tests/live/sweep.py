#!/usr/bin/env python3
"""Call every registered tool against a live Drupal site and classify the result.

This is the harness that found every real bug in this package so far — the six
dead tools, the `ddev_setup` docroot bug, the empty-body parse error, and the
layout_builder tools requesting a resource that has never existed. Offline tests
did not catch any of them, because they cannot exercise a real Drupal.

    python tests/live/sweep.py            # every tool
    python tests/live/sweep.py composer_  # tools whose name contains that

Verdicts:

    OK        returned usable data
    REJECTED  the tool answered, and the answer was a refusal or a lookup miss
    UPSTREAM  needs a module this site does not have (Commerce, Webform, ...)
    BLOCKED   needs a local binary that is not installed (phpstan, ollama, ...)
    DEAD      the tool itself is broken
    SKIPPED   controls the environment the sweep runs against (see ENV_CONTROL)

DEAD is reserved for product bugs. Anything environmental lands in BLOCKED or
UPSTREAM so that a missing module never hides a broken tool.
"""

from __future__ import annotations

import asyncio
import collections
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parents[2]
BASE = os.environ.get("DRUPAL_BASE_URL", "https://drupal-live.ddev.site")
VENV = HERE / "venv"

# Tools that start, stop, or reconfigure the very environment the sweep runs
# against. ddev_stop genuinely works — which is the problem: it takes the site
# down and every tool after it times out instead of reporting.
ENV_CONTROL = {
    "ddev_start", "ddev_stop", "ddev_restart", "ddev_delete",
    "lando_start", "lando_stop", "lando_rebuild", "lando_destroy",
    "lando_exec", "lando_shell",
}

# Names that shell out rather than call JSON:API. They need far more headroom:
# a single `ddev drush` invocation takes 24-66s.
LOCAL_TOOL = re.compile(
    r"^(drush_|ddev_|lando_|acquia_|composer_|cache_|backup_|cron_|queue_"
    r"|code_audit|drupal_check|code_sniffer|deprecation_scan|security_audit"
    r"|composer_audit|code_quality_report|security_scan|dependency_scan"
    r"|performance_|test_run|test_scaffold|test_coverage|test_list"
    r"|module_|theme_|ai_|bulk_update_aliases)"
)

# Tools that shell out rather than call JSON:API. They need far more headroom:
# a single `ddev drush` invocation takes 24-66s on a healthy machine, and far
# longer when the host is loaded. SWEEP_TIMEOUT scales both budgets, so a
# congested machine can raise it rather than filing every slow tool BLOCKED.
_LOCAL_TIMEOUT = int(os.environ.get("SWEEP_LOCAL_TIMEOUT", "150"))
_JSONAPI_TIMEOUT = int(os.environ.get("SWEEP_JSONAPI_TIMEOUT", "45"))


def TIMEOUT(local: bool) -> int:
    return _LOCAL_TIMEOUT if local else _JSONAPI_TIMEOUT


# The modules this site has. Commerce, Webform, Paragraphs, Metatag, Feeds and
# Search API are all installed, so tools needing them report a real result
# rather than UPSTREAM; the ones genuinely absent here are listed in
# tests/live/README.md.
UPSTREAM_MODULES = (
    "Pathauto patterns and redirects are not installed here."
)

# Tools that write. They keep synthetic ids so the sweep cannot rewrite the
# site's views, menus and fields out from under the tools that run after them.
#
# Structural updates are included on purpose: `views_update` with a real view
# id would save the view back with the arguments the harness synthesised, and
# every later `views_execute` would then run against a view this run broke.
MUTATING = re.compile(
    r"_(create|update|delete|revert|truncate|purge|remove|place|attach|detach"
    r"|enable|disable|import|rollback|clear|reindex|publish|unpublish"
    r"|block|unblock|approve|unapprove|cancel|abort|spam|assign|promote"
    r"|demote|rebuild|install|uninstall|flush|wipe|reset|restore|save)$"
)

# The parameters whose names really do mean "the id of a content entity", and
# so can be answered with a node that exists. Everything else ending in `id`
# names some other resource, and gets junk instead: asking `view_id` for a
# node number tests nothing but the miss.
_CONTENT_ENTITY_ID = {"entity_id", "revision_id_1", "revision_id_2"}

# A real id for each resource the site has, handed to read-only tools.
#
# Every parameter ending in "id" used to be answered with the fixture node's
# id, so `view_id`, `menu_id`, `webform_id` and 80-odd others were all sent
# "7" and answered a lookup miss. That was 84 of 174 refusals in the last run:
# not tools refusing, but the harness asking the wrong question. A miss tells
# you nothing about whether the tool works.
FIXTURE_ID = {
    "view_id": "content",
    "display_id": "page_1",
    "menu_id": "main",
    "webform_id": "contact",
    "media_type_id": "image",
    "type_id": "basic",  # paragraphs_type
    "transition_id": "create_new_draft",
    "workflow_id": "editorial",
    # The editorial workflow's states. This site has no `content_moderation_state`
    # config entities of its own -- they come from the workflow -- so naming one
    # is the only way moderation_state_get reaches its own logic.
    "state_id": "draft",
    "form_id": "personal",  # contact_form
    "pattern_id": "article",  # pathauto_pattern
    "server_id": "database",  # search_api_server
    "index_id": "content",  # search_api_index
    "store_id": "default",  # commerce_store
    "block_id": "claro_content",
    "format_id": "basic_html",  # filter_format
    "style_id": "thumbnail",  # image_style
    "date_format_id": "html_date",
    "role_id": "authenticated",
    "language_id": "fr",
    "node_type_id": "article",
    "vocabulary_id": "tags",
    "action_id": "comment_save_action",
    "breakpoint_id": " breakpoint.user",
    "plugin_id": "field",
    "machine_name": "sweep_probe",
    # Entities this site has none of. Naming one is still more honest than a
    # node id: the refusal reads "no comment with id 1", which is the truth
    # about the fixture rather than about the tool.
    "comment_id": "1",
    "submission_id": "1",
    "message_id": "1",
    "paragraph_id": "1",
    "item_id": "1",
    "revision_id": "1",
    "migration_id": "1",
    "redirect_id": "1",
    "feed_id": "1",
}

# One parameter name can mean several resources, and only the tool's own name
# says which: `config_id` is a field config, a metatag config or a search
# index depending on who is asking.
FIXTURE_BY_TOOL = {
    "field_config_": {"config_id": "media.image.field_media_image"},
    "field_storage_": {"config_id": "media.field_media_image"},
    "metatag_config_": {"config_id": "node.article"},
    "search_api_index_": {"index_id": "content"},
    "paragraphs_type_": {"type_id": "basic"},
    "views_": {"view_id": "content", "display_id": "page_1"},
    "menu_link_": {"menu_id": "main"},
    "webform_handler_": {"webform_id": "contact"},
    "webform_element_": {"webform_id": "contact"},
    "webform_submission_": {"webform_id": "contact"},
    "moderation_transition_": {"workflow_id": "editorial"},
    "moderation_state_": {"workflow_id": "editorial"},
    "workflow_": {"workflow_id": "editorial"},
}

DEAD_PATTERNS = [
    "unexpected keyword argument",
    "coroutine",
    "takes N positional argument",
    "AttributeError",
    "NameError",
    "ImportError",
    # The tool built a command line drush itself refuses. Db_tables, db_query,
    # db_count, drush_php_eval and every `ev` tool failed this way once
    # DrushClient shlex-split their arguments into separate tokens.
    "too many arguments",
    # The tool emitted PHP that PHP rejects. queue_create's `\$queue = ...`
    # leaked a shell escape into a non-shell context and died with a ParseError
    # on every call.
    "parseerror",
    "syntax error, unexpected",
    # The tool called an API that does not exist. cron_list asked for
    # Drupal 7's drupal_get_cron_jobs(), removed in Drupal 8.
    "undefined function",
    "undefined method",
]


def resolve_schema(spec: dict):
    """Return ``(type, spec)`` for the first non-null branch of a union.

    FastMCP emits ``list[str] | None`` as ``{"anyOf": [{"type": "array", ...},
    {"type": "null"}]}`` with no top-level ``type``. Reading only ``type``
    leaves it ``None``, which falls through every branch and sends the string
    "sweep_value" where a list was required, so FastMCP rejects the call before
    the tool body ever runs. That produced ~40 false REJECTED verdicts per run.
    """
    if spec.get("type"):
        return spec["type"], spec
    for alt in spec.get("anyOf") or spec.get("oneOf") or []:
        if isinstance(alt, dict) and alt.get("type") not in (None, "null"):
            return alt["type"], alt
    return None, spec


# A parameter the harness deliberately leaves out of the call instead of
# sending a value Drupal will refuse for reasons unrelated to the tool.
_OMIT = object()


def synthesize(schema: dict, tool: str = "") -> dict:
    """Build plausible arguments from a tool's JSON schema."""
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    out: dict = {}
    for name, spec in props.items():
        t, resolved = resolve_schema(spec)
        default = spec.get("default")
        value = default if default is not None else value_for(name, t, resolved, tool)
        if value is _OMIT:
            # Only a caller who could leave the argument out can have it left
            # out. A required one still has to be filled, and "en" is a
            # language Drupal accepts, where the junk value would have made
            # the tool answer a permission error about the field instead of
            # doing its job.
            if name not in required:
                continue
            value = "en"
        out[name] = value
    return out


def value_for(name: str, t, spec: dict, tool: str = ""):
    n = name.lower()
    enum = spec.get("enum")
    if enum:
        return enum[0]

    # JSON:API write-protects `langcode` on a site that has content_translation
    # installed but no bundle configured for translation, so sending a value
    # answers 403 "the current user is not allowed to POST the selected field
    # (langcode)" whatever that value is -- "en" as much as "sweep_value". A
    # careful client omits it, and the create then succeeds; sending one here
    # tested nothing but Drupal's permission message and cost create_term a
    # clean verdict.
    if n == "langcode":
        # The interface translation tools are the exception: they operate on
        # locale's target-language rows, and this site's translations are
        # French. Omitting the language there lists nothing and writing one
        # would create an English translation of English source text.
        if tool.startswith("interface_translation_"):
            return "fr"
        return _OMIT
    # Drush's watchdog filters are an enumerated type and a severity number;
    # "sweep_value" is neither, so the command is refused before it runs.
    if n == "type_filter":
        return "access denied"
    if n == "severity":
        return "7"
    if n in ("config_name",):
        # `{entity_type}/{entity_id}` for a config entity every site with
        # content types has. Without the slash the config translation tools
        # stop at the reference format and never reach their own logic.
        return "node_type/article"
    if "fields" in n:
        # The payload Drupal validates. An empty one answers "title is
        # required" on a create and is a silent no-op on an update that still
        # reports OK -- so the tool was never exercised either way. Answered
        # up here, before the type rules: a nested object resolves to `object`,
        # which used to be sent `{}` and shadow this rule entirely.
        return {"title": "Sweep Title"}
    if n in ("queue_name", "queue") and EXISTING_QUEUE:
        # A queue that exists, so queue_run exercises the run rather than
        # stopping at "Queue not found" for a name nobody chose.
        return EXISTING_QUEUE
    if "command" in n and tool in ("ddev_exec", "lando_exec"):
        # These run the argument inside the container, where `status` -- the
        # right answer for drush_command -- is not a command at all.
        return "php -v"
    # A read-only tool is handed an id that exists, so its answer is about the
    # tool rather than about a lookup miss. See FIXTURE_ID for why.
    if not MUTATING.search(tool):
        # Where one parameter name covers several resources, the tool's own
        # name says which one it means, so that is consulted first.
        for prefix, mapping in FIXTURE_BY_TOOL.items():
            if tool.startswith(prefix) and name in mapping:
                return mapping[name]
        if name in FIXTURE_ID:
            return FIXTURE_ID[name]
    if isinstance(t, list):
        t = next((x for x in t if x and x != "null"), None)
    if t == "boolean":
        return False
    if t == "integer":
        return 5 if ("limit" in n or "count" in n or "page" in n) else 1
    if t == "number":
        return 1
    if t == "array":
        return []
    if t == "object":
        return {}

    # Named ids must be matched before the generic endswith("id") rule, or
    # `vid` becomes "1" and every taxonomy tool 404s for the wrong reason.
    if n in ("nid", "node_id"):
        return EXISTING_NID
    if n in ("uid", "user_id"):
        # Deliberately NOT uid=1: blocking or deleting admin mid-sweep breaks
        # the session auth every later tool depends on.
        return "2"
    if n in ("tid", "term_id"):
        return "1"
    if n in ("vid", "vocabulary", "vocabulary_id"):
        return "tags"
    if n in ("project_id", "project", "machine_name"):
        # drupal.org tools want a machine name; "1" 404s every one of them.
        return "pathauto"
    if n.endswith("id"):
        # Only a parameter that genuinely names a content entity gets a live
        # node. Before this, `view_id`, `menu_id` and `webform_id` were all
        # answered with a node number, which is where 84 of the last run's
        # 174 refusals came from.
        return EXISTING_NID if n in _CONTENT_ENTITY_ID else "sweep_value"
    if n in ("bundle", "content_type", "type", "resource_type"):
        return "article"
    if n in ("entity_type",):
        # Must be an entity type, not a bundle: revision tools build
        # "<type>--<type>" and a bundle here 404s for reasons unrelated
        # to the tool under test.
        return "node"
    if n in ("media_type",):
        return "image"
    if "uuid" in n:
        return "4d9ecad4-49d5-481d-bf4e-8cfe9fde5471"
    if "path" in n:
        return "/tmp/sweep-file.txt"
    if "url" in n or "uri" in n:
        return f"{BASE}/jsonapi"
    if "query" in n and "sql" not in n:
        return "{ __typename }"
    if "sql" in n:
        return "SELECT 1"
    if "command" in n:
        return "status"
    if "name" in n:
        return "sweep_name"
    if "mail" in n or "email" in n:
        return "sweep@example.test"
    if "title" in n:
        return "Sweep Title"
    if "body" in n:
        # Every `body` parameter in this package is a plain string; the tools
        # wrap it into Drupal's {value, format} shape themselves.
        return "<p>sweep body</p>"
    if "filters" in n:
        return {}
    if "updates" in n:
        return {"title": "Sweep Updated"}
    if "variables" in n or "options" in n or "params" in n:
        return {}
    if "includes" in n or "include" in n:
        return []
    if "sorts" in n:
        return []
    return "sweep_value"


def _verdict_for(detail: str) -> str:
    low = detail.lower()
    if re.search(r"\b(module|plugins are not enabled|unknown option)\b", low):
        return "UPSTREAM"
    if "not available" in low or "not found" in low or "command not found" in low:
        return "BLOCKED"
    if any(pattern.lower() in low for pattern in DEAD_PATTERNS):
        return "DEAD"
    return "REJECTED"


def classify(payload, tool_name: str, local: bool):
    """Decide what a tool's answer means."""
    if isinstance(payload, dict):
        if payload.get("error"):
            detail = str(payload["error"])
            return _verdict_for(detail), detail[:200]
        # A failed drush run returns {returncode: 1, stderr: "..."} with no
        # `error` key at all. Before this branch every such tool was counted
        # OK, so db_tables, db_query, db_count, drush_php_eval and every `ev`
        # tool reported as passing while drush answered "Too many arguments".
        rc = payload.get("returncode")
        if rc not in (None, 0):
            detail = str(payload.get("stderr") or "").strip() or f"command exited {rc}"
            detail = " ".join(detail.split())
            return _verdict_for(detail), detail[:200]
    if isinstance(payload, str) and "Error calling tool" in payload:
        if any(pattern.lower() in payload.lower() for pattern in DEAD_PATTERNS):
            return "DEAD", payload[:200]
        return "REJECTED", payload[:200]
    return "OK", ""


def _origin() -> str:
    """The scheme, host and port this run is actually talking to.

    Drupal builds its own links from the request it saw, so a site fronted by
    a port-mapped HTTPS endpoint hands back `http://` URLs. Following one of
    those to the HTTPS port sends a plain request to a TLS listener and nginx
    answers 400 -- which is how the sweep used to die before calling a single
    tool. Anchoring every follow on BASE keeps the run on the origin it was
    given, whatever origin the site thinks it has.
    """
    parts = urllib.parse.urlsplit(BASE)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def _reanchor(href: str) -> str:
    """Point a link the site generated at the origin this run was given."""
    if "://" not in href:
        return href
    scheme, netloc, *_ = urllib.parse.urlsplit(_origin())
    parts = urllib.parse.urlsplit(href)
    return urllib.parse.urlunsplit((scheme, netloc, parts.path, parts.query, ""))


def _get(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.api+json"})
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, context=ctx, timeout=timeout) as response:
        return json.load(response)


_NODE_COLLECTIONS: list[str] | None = None


def node_collections() -> list[str]:
    """Collection URLs for every node bundle this site exposes.

    JSON:API has no cross-bundle collection. The resource name in the index
    (`node--article`) is not its path (`/jsonapi/node/article`), and a row is
    addressed by uuid rather than by the internal id the harness holds -- so
    neither `/jsonapi/node--article/8` nor `/jsonapi/node/article/8` can
    answer "is this node still here". The bundles cannot change during a
    sweep, so the index is read once.

    Raises whatever the index request raised; the caller decides whether that
    is evidence of anything.
    """
    global _NODE_COLLECTIONS
    if _NODE_COLLECTIONS is None:
        index = _get(f"{BASE}/jsonapi")
        urls: list[str] = []
        for key, link in (index.get("links") or {}).items():
            if not key.startswith("node--"):
                continue
            href = link.get("href") if isinstance(link, dict) else link
            if href:
                urls.append(_reanchor(href))
        _NODE_COLLECTIONS = urls
    return _NODE_COLLECTIONS


def pick_live_nid() -> str:
    """Ask the site for a node that actually exists."""
    for url in node_collections():
        rows = _get(f"{url}?page%5Blimit%5D=1&sort=created").get("data") or []
        if rows:
            return str(rows[0]["attributes"].get("drupal_internal__nid") or "1")
    return "1"


EXISTING_NID = "1"
# Filled in from queue_list before the sweep starts, so queue_run exercises a
# queue the site actually has.
EXISTING_QUEUE = ""


def node_exists(nid: str) -> bool:
    """Ask JSON:API whether the fixture node is still there.

    `delete_node` runs during the sweep and takes the fixture with it, so
    every tool that ran after it got a 404 for a node this harness deleted --
    revision_list, revision_get, revision_revert, revision_diff,
    translation_status, translation_add, moderation_transition_execute,
    layout_builder_override_remove and accessibility_aria_validate all failed
    for that reason alone. Checking before the tools that need the id lets
    the fixture be re-provisioned instead of silently rotting.

    The question is asked as a filter, because there is no direct one: rows
    are addressed by uuid, and the obvious `/jsonapi/node--article/{nid}`
    builds the resource *name* into the path, which 404s for every node and
    used to make the fixture look permanently gone.
    """
    try:
        urls = node_collections()
    except Exception:
        # The index could not be read. A timeout or a network blip is not
        # evidence that the node is gone, and re-provisioning on one would
        # churn the fixture for nothing.
        return True
    if not urls:
        # The index read cleanly and exposes no node bundle, so there is
        # nowhere for this id to live.
        return False
    for url in urls:
        query = f"{url}?filter%5Bdrupal_internal__nid%5D={nid}&page%5Blimit%5D=1"
        try:
            if _get(query, timeout=20).get("data"):
                return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                # This bundle's path does not resolve, which says nothing
                # about the others -- keep asking them.
                continue
            # A 5xx is the server failing to answer, not the node being gone.
            return True
        except Exception:
            return True
    return False


def refresh_nid_if_gone() -> str:
    """Re-provision the fixture node if a tool deleted it mid-sweep."""
    global EXISTING_NID
    if EXISTING_NID and not node_exists(EXISTING_NID):
        print(f"node {EXISTING_NID} was deleted mid-sweep; re-provisioning", flush=True)
        EXISTING_NID = str(pick_live_nid())
        print(f"using node {EXISTING_NID} for id arguments", flush=True)
    return EXISTING_NID


def _takes_a_node_id(schema: dict) -> bool:
    """Whether this tool will be handed the fixture node's id.

    Checking the declared parameter names rather than the resolved value
    keeps the check free of the same `endswith("id")` guessing that made the
    fixture wrong in the first place.
    """
    props = schema.get("properties") or {}
    return any(name in props for name in ("nid", "node_id"))


async def find_queue(session) -> str:
    """Return the name of a queue that exists on this site, or ""."""
    try:
        res = await session.call_tool("queue_list", {}, read_timeout_seconds=30)
        text = "".join(getattr(c, "text", "") for c in res.content)
        payload = json.loads(text)
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, dict) and data:
            return str(next(iter(data)))
        if isinstance(data, list) and data:
            return str(data[0])
    except Exception:
        pass
    return ""


async def main() -> int:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    env = dict(os.environ)
    env.update({
        "DRUPAL_BASE_URL": BASE,
        "DRUPAL_USERNAME": os.environ.get("DRUPAL_USERNAME", "admin"),
        "DRUPAL_PASSWORD": os.environ.get("DRUPAL_PASSWORD", "admin"),
        "DRUPAL_VERIFY_SSL": "false",
        "MCP_LOG_LEVEL": "ERROR",
        # Drush lives in the DDEV container, so the server must be started
        # from the project directory with a multi-word drush command.
        "DRUSH_PATH": "ddev drush",
    })
    # The server must start in the DDEV project directory: the ddev_*, lando_*
    # and composer_* tools run in their own cwd, and `ddev drush` only resolves
    # inside the project.
    project = HERE / "drupal-live"
    params = StdioServerParameters(
        command="sh",
        args=["-c", f"cd {project} && exec {VENV}/bin/drupal-mcp"],
        env=env,
    )

    results = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            # JSON:API returns drupal_internal__nid as an int; tools declare
            # `nid: str`, so pydantic rejects it with string_type before the
            # body ever runs. Coerce it.
            global EXISTING_NID, EXISTING_QUEUE
            EXISTING_NID = str(pick_live_nid())
            EXISTING_QUEUE = await find_queue(session)
            print(f"using node {EXISTING_NID} for id arguments", flush=True)
            if EXISTING_QUEUE:
                print(f"using queue {EXISTING_QUEUE} for queue arguments", flush=True)
            if only:
                tools = [t for t in tools if only in t.name]
            print(f"sweeping {len(tools)} tools against {BASE}\n", flush=True)

            for i, t in enumerate(tools, 1):
                if t.name in ENV_CONTROL:
                    results.append({
                        "tool": t.name,
                        "verdict": "SKIPPED",
                        "detail": "controls the environment the sweep runs against",
                        "elapsed": 0,
                    })
                    continue
                # The MCP SDK renamed `inputSchema` to `input_schema`. Read
                # either so a client upgrade does not abort the whole sweep.
                schema = getattr(t, "inputSchema", None) or getattr(t, "input_schema", None) or {}
                # `delete_node` may have taken the fixture with it, and every
                # tool that names a node id from here on would 404 for a reason
                # that has nothing to do with the tool under test.
                if _takes_a_node_id(schema):
                    refresh_nid_if_gone()
                args = synthesize(schema, t.name)
                local = bool(LOCAL_TOOL.match(t.name))
                timeout = TIMEOUT(local)
                start = time.time()
                try:
                    res = await session.call_tool(t.name, args, read_timeout_seconds=timeout)
                    text = "".join(getattr(c, "text", "") for c in res.content)
                    try:
                        payload = json.loads(text)
                    except Exception:
                        payload = text
                    verdict, detail = classify(payload, t.name, local)
                    # A call the server refused is not a passing one. When the
                    # arguments fail FastMCP's validation the answer is prose
                    # rather than JSON, so no pattern in classify() matches it
                    # and the fall-through says OK: translation_add,
                    # translation_update, the three interface_translation_*
                    # tools and config_translation_add were counted OK on every
                    # run while never being called at all.
                    if verdict == "OK" and (
                        getattr(res, "isError", False)
                        or getattr(res, "is_error", False)
                    ):
                        verdict, detail = "REJECTED", " ".join(text.split())[:200]
                except TimeoutError:
                    verdict, detail = "BLOCKED", f"timeout >{timeout}s"
                except Exception as e:
                    # The MCP SDK raises its own error type for a read timeout,
                    # not TimeoutError, so without this branch the two slowest
                    # tools -- a real composer update, and drush's
                    # config:security:check pulling advisories off drupal.org --
                    # were filed DEAD for taking longer than the budget the
                    # sweep allows them, which is not what DEAD means.
                    if "timed out" in str(e).lower():
                        verdict, detail = "BLOCKED", f"timeout >{timeout}s"
                    else:
                        verdict, detail = "DEAD", f"{type(e).__name__}: {str(e)[:200]}"

                elapsed = time.time() - start
                results.append({
                    "tool": t.name,
                    "verdict": verdict,
                    "detail": detail,
                    "elapsed": round(elapsed, 1),
                })
                if i % 25 == 0:
                    print(f"  ...{i}/{len(tools)}", flush=True)

    counts = collections.Counter(r["verdict"] for r in results)
    print("\n" + "=" * 60)
    print("SWEEP RESULTS")
    print("=" * 60)
    for verdict in ["OK", "REJECTED", "UPSTREAM", "BLOCKED", "DEAD", "SKIPPED"]:
        print(f"  {verdict:9s} {counts.get(verdict, 0)}")
    print(f"  {'TOTAL':9s} {len(results)}")

    for verdict in ["DEAD", "UPSTREAM"]:
        rows = [r for r in results if r["verdict"] == verdict]
        if not rows:
            continue
        print(f"\n{verdict} ({len(rows)}):")
        for r in rows[:60]:
            print(f"  {r['tool']:34s} {r['detail'][:60]!r}")
        if verdict == "UPSTREAM":
            print(f"\n  {UPSTREAM_MODULES}")

    out = HERE / "tests" / "live" / "sweep-results.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nfull results written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
