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

# Modules this site deliberately does not install, so tools that need them
# report UPSTREAM rather than FAILING like broken code.
UPSTREAM_MODULES = (
    "Commerce, Paragraphs, Webform, Search API, Feeds, Metatag, Pathauto "
    "patterns, redirect, and the translation modules are not installed here."
)

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


def synthesize(schema: dict) -> dict:
    """Build plausible arguments from a tool's JSON schema."""
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    out: dict = {}
    for name, spec in props.items():
        t, resolved = resolve_schema(spec)
        default = spec.get("default")
        if name in required and default is None:
            out[name] = value_for(name, t, resolved)
        elif default is not None:
            out[name] = default
        else:
            out[name] = value_for(name, t, resolved)
    return out


def value_for(name: str, t, spec: dict):
    n = name.lower()
    enum = spec.get("enum")
    if enum:
        return enum[0]
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
        return EXISTING_NID
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
    if "fields" in n:
        return {"title": "Sweep Title"}
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


def pick_live_nid() -> str:
    """Ask the site for a node that actually exists.

    JSON:API has no /jsonapi/node collection - every content entity is
    addressed per bundle - so the bundle has to come from the index first.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    def get(url: str):
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.api+json"})
        with urllib.request.urlopen(req, context=ctx, timeout=30) as response:
            return json.load(response)

    index = get(f"{BASE}/jsonapi")
    for key, link in (index.get("links") or {}).items():
        if not key.startswith("node--"):
            continue
        href = link.get("href") if isinstance(link, dict) else link
        if not href:
            continue
        rows = get(f"{href}?page%5Blimit%5D=1&sort=created").get("data") or []
        if rows:
            return str(rows[0]["attributes"].get("drupal_internal__nid") or "1")
    return "1"


EXISTING_NID = "1"


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
            global EXISTING_NID
            EXISTING_NID = str(pick_live_nid())
            print(f"using node {EXISTING_NID} for id arguments", flush=True)
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
                args = synthesize(schema)
                local = bool(LOCAL_TOOL.match(t.name))
                timeout = 150 if local else 45
                start = time.time()
                try:
                    res = await session.call_tool(t.name, args, read_timeout_seconds=timeout)
                    text = "".join(getattr(c, "text", "") for c in res.content)
                    try:
                        payload = json.loads(text)
                    except Exception:
                        payload = text
                    verdict, detail = classify(payload, t.name, local)
                except TimeoutError:
                    verdict, detail = "BLOCKED", f"timeout >{timeout}s"
                except Exception as e:
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

    out = HERE / "tests" / "live" / "sweep-results.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nfull results written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
