"""Shared utilities for tool modules."""

import json
from typing import Any


def drush_output(result: dict[str, Any]) -> str:
    """Human-readable output from a DrushClient result.

    DrushClient parses stdout into ``data`` and has no ``stdout`` key, so
    reading ``result["stdout"]`` always produced an empty string.
    """
    data = result.get("data")
    if isinstance(data, dict):
        if isinstance(data.get("output"), str):
            return data["output"]
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
