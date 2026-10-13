"""Shared utilities for tool modules."""

from typing import Any


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
