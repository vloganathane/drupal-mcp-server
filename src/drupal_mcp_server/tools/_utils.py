"""Shared utilities for tool modules."""

import asyncio
import json
import os
import shutil
from typing import Any

_COMPOSER_TIMEOUT = 900


async def run_composer(args: list[str]) -> dict[str, Any]:
    """Run the composer binary and report what happened.

    Drush has no ``composer`` command, so routing these tools through it made
    all four fail with ``Command "composer" is not defined``. Composer is its
    own executable; look for it rather than borrowing Drush.
    """
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

    argv = [binary, *args, "--no-interaction"]
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
        return {"returncode": 127, "output": "", "error": f"could not run {binary}: {exc}"}

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
    """
    if result is None:
        return {"error": "No response"}
    if isinstance(result, list):
        return {"data": result}
    return result


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
