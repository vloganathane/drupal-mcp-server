"""Shared utilities for tool modules."""

import asyncio
import base64
import csv
import json
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# JSON:API accepts page sizes up to 200 on stock Drupal; larger pages are
# clamped to the configured maximum, so the pager also treats an empty or
# short page as the end rather than trusting the requested size.
_PAGE = 200
# Hard stop per bundle: 500 pages x 200 rows = 100,000 entities.
_MAX_PAGES = 500
# Per-value cap for the free-form `fields` column so one body value cannot
# produce a multi-megabyte CSV row.
_FIELD_CAP = 5000
_PREVIEW_ROWS = 3
_PREVIEW_CAP = 120

_COMPOSER_TIMEOUT = 900


def b64_text(value: Any) -> str:
    """Encode a value for safe transport into a PHP double-quoted context.

    PHP has no ``\\uXXXX`` escape - it is an error there, not an unknown
    sequence - so a non-ASCII label interpolated into a PHP string mangles
    silently, and a quote or backslash breaks the statement outright. Base64
    sidesteps both: PHP reads it back with ``base64_decode()`` and the text
    survives exactly. The value is also then inert to the shell and to Drush's
    own argument parsing, so no escaping is needed anywhere along the path.
    """
    return base64.b64encode(str(value).encode("utf-8")).decode("ascii")


def php_text(value: Any) -> str:
    """A PHP expression that evaluates to ``value`` as a string, exactly.

    Interpolating ``json.dumps(value)`` into PHP is not safe: JSON escapes are
    not PHP escapes, so a French label comes out as the literal six characters
    ``\u00e9``, and any ``$`` in the text starts a PHP variable interpolation
    that quietly eats the rest of the word. Base64 has neither problem, so the
    whole value is handed over as ``base64_decode('...')``.
    """
    return "base64_decode('" + b64_text(value) + "')"


def php_json(value: Any) -> str:
    """A PHP expression that evaluates to ``value`` as a PHP array or scalar.

    For anything that is not a plain string -- a list of ids, a dict of
    configuration -- because a JSON object literal is not a PHP array literal
    at all: both ``{}`` and ``{"k": 1}`` are parse errors there.
    """
    return (
        "json_decode(base64_decode('" + b64_text(json.dumps(value)) + "'), TRUE)"
    )


def _working_dir(args: list[str]) -> str:
    for arg in args:
        if isinstance(arg, str) and arg.startswith("--working-dir="):
            return arg.split("=", 1)[1]
    return "."


def _container_composer(args: list[str]) -> list[str] | None:
    """A container-prefixed composer command, or None to use a local binary.

    Dependencies for a container-based project have to be resolved against the
    *container's* PHP, not the host's. Running the host composer here resolved
    `doctrine/collections` against PHP 8.4 and locked in a release that requires
    it, while the container runs 8.3; Composer's platform check then aborted
    every subsequent PHP request, taking the site down. `ddev composer` and
    `lando composer` run inside the container and so resolve correctly.
    """
    directory = _working_dir(args)
    if shutil.which("ddev") and os.path.isdir(os.path.join(directory, ".ddev")):
        return ["ddev", "composer"]
    if shutil.which("lando") and os.path.exists(os.path.join(directory, ".lando.yml")):
        return ["lando", "composer"]
    return None


async def run_composer(args: list[str], tail: int | None = 4000) -> dict[str, Any]:
    """Run composer and report what happened.

    Drush has no ``composer`` command, so routing these tools through it made
    all four fail with ``Command "composer" is not defined``. Composer is its
    own executable; look for it rather than borrowing Drush. For a DDEV or
    Lando project the container's own composer is used instead.

    ``tail`` bounds how much of stdout is kept: enough for a human-readable
    report, and it is what makes a runaway command cheap to return. A tool
    that parses the whole JSON document passes ``tail=None`` instead, since
    the tail of a large ``outdated --format=json`` is not parseable JSON.
    """
    argv = _container_composer(args)
    binary: str | None = None
    if argv is None:
        binary = shutil.which("composer")
        if binary is None:
            for candidate in ("./vendor/bin/composer", "./bin/composer"):
                if os.path.exists(candidate):
                    binary = candidate
                    break
        if binary is None:
            return {
                "returncode": 127,
                "output": "",
                "error": (
                    "composer is not on PATH and no ./vendor/bin/composer was "
                    "found next to the working directory. Install Composer from "
                    "https://getcomposer.org, or start the MCP server from the "
                    "project root."
                ),
            }
        argv = [binary]

    argv = [*argv, *args, "--no-interaction"]
    command = " ".join(argv)
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=_COMPOSER_TIMEOUT
        )
    except TimeoutError:
        return {
            "returncode": -1,
            "output": "",
            "error": f"composer timed out after {_COMPOSER_TIMEOUT}s",
            "command": command,
        }
    except OSError as exc:
        return {"returncode": 127, "output": "", "error": f"could not run {argv[0]}: {exc}"}

    text = stdout.decode(errors="replace")
    payload: dict[str, Any] = {
        "returncode": proc.returncode,
        "output": text if tail is None else text[-tail:],
        "command": command,
    }
    if proc.returncode:
        reason = stderr.decode(errors="replace").strip() or text.strip()
        payload["error"] = (reason or "composer failed with no output")[:800]
    return payload


def jsonapi_attrs(item: dict[str, Any]) -> dict[str, Any]:
    """The attributes object of a JSON:API resource, or an empty dict."""
    attributes = item.get("attributes")
    return attributes if isinstance(attributes, dict) else {}


def jsonapi_bundle(item: dict[str, Any]) -> str:
    """Bundle machine name from a resource type like ``node--article``."""
    type_name = str(item.get("type", ""))
    return type_name.split("--", 1)[1] if "--" in type_name else ""


def jsonapi_rel_ids(item: dict[str, Any], relationship: str) -> list[str]:
    """UUIDs referenced by one relationship (single or to-many)."""
    relationships = item.get("relationships")
    rel = relationships.get(relationship) if isinstance(relationships, dict) else None
    if not isinstance(rel, dict):
        return []
    data = rel.get("data")
    if isinstance(data, dict):
        return [str(data.get("id"))] if data.get("id") else []
    if isinstance(data, list):
        return [str(row.get("id")) for row in data if isinstance(row, dict) and row.get("id")]
    return []


async def jsonapi_collect(
    jsonapi: Any,
    resource_type: str,
    params: dict[str, Any],
    max_items: int = 0,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], bool]:
    """Page through one bundle collection.

    Returns ``(items, included-by-uuid, stopped-early)``; stopped-early is
    set when the item budget or the page cap ended the scan. Pagination
    runs per bundle: the JSON:API endpoint for a bare entity type merges
    every bundle behind one shared offset, which would silently skip rows
    when the pager walked the merged list. ``max_items`` is a fetch
    budget; callers trim to their exact row budget themselves.
    """
    items: list[dict[str, Any]] = []
    included: dict[str, dict[str, Any]] = {}
    offset = 0
    for _ in range(_MAX_PAGES):
        if max_items and len(items) >= max_items:
            return items, included, True
        page_params: dict[str, Any] = {
            **params,
            "page[limit]": str(_PAGE),
            "page[offset]": str(offset),
        }
        doc = await jsonapi.get_resource(resource_type, page_params)
        rows = doc.get("data") if isinstance(doc, dict) else None
        if not isinstance(rows, list) or not rows:
            break
        items.extend(row for row in rows if isinstance(row, dict))
        if isinstance(doc, dict):
            for extra in doc.get("included") or []:
                if isinstance(extra, dict) and extra.get("id"):
                    included[str(extra["id"])] = extra
        if len(rows) < _PAGE:
            break
        offset += len(rows)
    else:
        return items, included, True
    return items, included, False


def flag_label(value: Any, positive: str, negative: str) -> str:
    """Status cell that stays empty when the value was not readable.

    An absent status must never be presented as "unpublished" or
    "blocked": not knowing and knowing it is false are different facts.
    """
    if value is None:
        return ""
    return positive if value else negative


def cap_value(value: Any) -> Any:
    """Cap every string in a JSON-ish value at `_FIELD_CAP` characters."""
    if isinstance(value, str):
        if len(value) <= _FIELD_CAP:
            return value
        return value[:_FIELD_CAP] + "...[truncated]"
    if isinstance(value, dict):
        return {key: cap_value(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [cap_value(inner) for inner in value]
    return value


def preview_value(value: Any) -> Any:
    """Shorten one preview cell so the response stays tiny."""
    if isinstance(value, str) and len(value) > _PREVIEW_CAP:
        return value[:_PREVIEW_CAP] + "..."
    return value


def safe_export_path(
    requested: str | None, default_stem: str, fmt: str, drupal_root: str | None
) -> tuple[Path | None, str | None]:
    """Resolve the destination, confined to safe roots.

    Allowed roots: the Drupal root, the system temp directory, and the
    user's home directory. The path is resolved first, so `..` segments
    and symlinks that leave a safe root are rejected rather than followed.
    """
    suffix = ".xlsx" if fmt == "xlsx" else ".csv"
    if requested is not None:
        if not requested.strip():
            return None, "output_path is empty"
        path = Path(requested.strip()).expanduser()
        if path.suffix.lower() not in (".csv", ".xlsx"):
            return None, f"output_path must end in .csv or .xlsx (got {path.name!r})"
        if path.suffix.lower() != suffix:
            return None, f"output_path ends in {path.suffix!r} but format is {fmt!r}; make them match"
    else:
        stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        if drupal_root:
            base = Path(drupal_root) / "exports"
        else:
            base = Path(tempfile.gettempdir()) / "drupal-mcp-exports"
        path = base / f"{default_stem}_{stamp}{suffix}"
    try:
        resolved = path.resolve()
    except OSError as exc:
        return None, f"Cannot resolve output_path: {exc}"
    roots = [Path(tempfile.gettempdir()).resolve(), Path.home().resolve()]
    if drupal_root:
        roots.append(Path(drupal_root).resolve())
    for root in roots:
        if resolved == root or resolved.is_relative_to(root):
            return resolved, None
    return None, (
        f"output_path must live inside the Drupal root, {tempfile.gettempdir()}, or your home "
        f"directory (got {resolved})"
    )


def write_file(
    path: Path, columns: list[str], rows: list[list[Any]], fmt: str
) -> dict[str, Any]:
    """Write rows to CSV/XLSX; returns the file statistics or an error."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "xlsx":
            # Imported lazily: CSV is the common case and should not pay
            # for an Excel library at import time.
            from openpyxl import Workbook

            workbook = Workbook(write_only=True)
            sheet = workbook.create_sheet("export")
            sheet.append(columns)
            for row in rows:
                sheet.append(["" if value is None else value for value in row])
            workbook.save(path)
        else:
            # utf-8-sig: a BOM so Excel detects UTF-8 and keeps accented
            # titles intact; other readers skip it.
            with path.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(columns)
                for row in rows:
                    writer.writerow(["" if value is None else value for value in row])
    except ImportError:
        return {
            "error": (
                "openpyxl is not installed; it is a normal dependency of drupal-mcp-server, so "
                "reinstall the package (or use format='csv')"
            )
        }
    except OSError as exc:
        return {"error": f"Could not write {path}: {exc}"}
    return {
        "file_path": str(path),
        "rows": len(rows),
        "columns": len(columns),
        "file_size_kb": round(path.stat().st_size / 1024, 1),
        "preview": [
            {name: preview_value(value) for name, value in zip(columns, row, strict=True)}
            for row in rows[:_PREVIEW_ROWS]
        ],
    }


def sql_output(result: dict[str, Any]) -> tuple[str, str | None]:
    """Raw stdout text and an error reason from a `sql:query` result.

    `sql:query` has no --format option at all, so the client cannot parse
    the rows itself: stdout arrives as raw text under ``{"output": ...}``
    (or an empty dict when the query returned nothing).
    """
    data = result.get("data")
    if isinstance(data, dict) and isinstance(data.get("output"), str):
        return data["output"], None
    if isinstance(data, str):
        return data, None
    if result.get("returncode"):
        return "", str(result.get("stderr", "")).strip() or "query failed"
    return "", None


def sql_rows(output: str, columns: list[str]) -> list[dict[str, Any]]:
    """Parse `drush sql:query` output: tab-separated values, no header row.

    Values arrive as text, and NULL is printed as those four characters, so
    a NULL langcode reads back as None. A value containing a tab splits into
    extra fields, which are joined back into the last column rather than
    shifting the rest of the row.
    """
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) > len(columns):
            parts = parts[: len(columns) - 1] + [
                "\t".join(parts[len(columns) - 1 :])
            ]
        while len(parts) < len(columns):
            parts.append("")
        rows.append(
            {
                column: (None if value == "NULL" else value)
                for column, value in zip(columns, parts, strict=False)
            }
        )
    return rows


def drush_output(result: dict[str, Any]) -> str:
    """Human-readable output from a DrushClient result.

    DrushClient parses stdout into ``data`` and has no ``stdout`` key, so
    reading ``result["stdout"]`` always produced an empty string.
    """
    data = result.get("data")
    if isinstance(data, dict):
        if isinstance(data.get("output"), str):
            return str(data["output"])
        return json.dumps(data, indent=2, default=str) if data else ""
    if isinstance(data, str):
        return data
    return str(result.get("stdout") or "")


def drush_result(result: dict[str, Any], **extra: Any) -> dict[str, Any]:
    """Report a DrushClient result, surfacing stderr when the command failed.

    Ten tools returned just the exit code, so a typo in a command and a
    permissions problem looked identical to the caller.
    """
    payload: dict[str, Any] = {"returncode": result.get("returncode")}
    payload.update(extra)
    payload["output"] = drush_output(result)
    if result.get("returncode"):
        reason = str(result.get("stderr", "")).strip() or "no error output"
        payload["error"] = f"drush failed: {reason[:800]}"
        if result.get("command"):
            payload["command"] = result["command"]
    return payload


def php_single_quote(value: str) -> str:
    """Quote a value as a PHP single-quoted literal.

    The performance, accessibility, and file-audit tools used to interpolate
    raw values into ``'...'`` PHP, so a quote in a URL or path ended the
    literal and whatever followed became code. They also wrote shell-era
    ``\\$`` escapes, but drush receives arguments through exec with no shell
    to eat the backslash -- PHP itself saw ``\\$db``.
    """
    escaped = str(value).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def ensure_dict(result: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
    """Ensure result is a dict, not a list.

    JSON:API list endpoints return a dict with a 'data' key containing a list.
    This helper passes through valid dict responses and wraps None as an error.

    A failed Drush run also used to pass through untouched: it arrives as
    ``{returncode: 1, data: {}, stderr: "..."}`` with no ``error`` key, which
    is exactly what an empty successful result looks like. Callers and MCP
    clients reading ``data`` therefore saw a broken command as "no rows", and
    the live sweep counted those tools as passing. The keys are all kept so
    nothing is lost; ``error`` is added alongside them.
    """
    if result is None:
        return {"error": "No response"}
    if isinstance(result, list):
        return {"data": result}
    if isinstance(result, dict) and result.get("returncode") not in (None, 0):
        reason = " ".join(str(result.get("stderr") or "").split()) or "no error output"
        return {**result, "error": f"drush failed: {reason[:800]}"}
    return result


def absent_entity(entity: str, explanation: str) -> dict[str, Any]:
    """Explain that a tool targets an entity type Drupal does not have.

    Thirteen tools ask JSON:API for `webform_handler`, `workflow_transition`,
    `feeds_log` or `interface_translation`. None of the four is an entity type
    at all: a webform's handlers are plugins configured on the webform, a
    workflow's transitions are configuration on the workflow, Feeds 3.x dropped
    its log entity, and Locale keeps interface translations in its own storage
    rather than exposing them. Each request 404'd, and a 404 reads exactly like
    a missing module, so these looked like environment problems rather than
    tools that cannot work on any site.
    """
    return {
        "error": (
            f"Drupal has no '{entity}' entity type, so this tool cannot work "
            f"against a correctly built site. {explanation}"
        ),
        "entity_type": entity,
    }


def langcode_field(langcode: str | None) -> dict[str, Any]:
    """Include `langcode` only when the caller asked for one.

    A default of ``"en"`` is harmless on a single-language site. On a
    multilingual one the field is writable only with translation permission, so
    always sending it makes every create fail 403 -- "the current user is not
    allowed to POST the selected field (langcode)" -- for anyone who cannot
    translate, including an ordinary authenticated user creating a term in the
    site's own language. Leaving it out lets Drupal apply the default.
    """
    return {"langcode": langcode} if langcode else {}


def validate_pagination(page_limit: int = 50, page_offset: int = 0) -> dict[str, Any] | None:
    """Validate pagination parameters. Returns error dict or None if valid."""
    if not isinstance(page_limit, int) or page_limit < 1 or page_limit > 500:
        return {"error": "page_limit must be an integer between 1 and 500"}
    if not isinstance(page_offset, int) or page_offset < 0:
        return {"error": "page_offset must be a non-negative integer"}
    return None


def build_pagination_params(page_limit: int = 50, page_offset: int = 0) -> dict[str, str]:
    """Build pagination params dict for JSON:API requests."""
    return {"page[limit]": str(page_limit), "page[offset]": str(page_offset)}
