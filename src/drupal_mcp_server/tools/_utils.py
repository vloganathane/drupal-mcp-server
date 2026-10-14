"""Shared utilities for tool modules."""

import asyncio
import base64
import json
import os
import shutil
from typing import Any

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


async def run_composer(args: list[str]) -> dict[str, Any]:
    """Run composer and report what happened.

    Drush has no ``composer`` command, so routing these tools through it made
    all four fail with ``Command "composer" is not defined``. Composer is its
    own executable; look for it rather than borrowing Drush. For a DDEV or
    Lando project the container's own composer is used instead.
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
        "output": text[-4000:],
        "command": command,
    }
    if proc.returncode:
        reason = stderr.decode(errors="replace").strip() or text.strip()
        payload["error"] = (reason or "composer failed with no output")[:800]
    return payload


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
