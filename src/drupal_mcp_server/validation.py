"""Reusable input validation for all tool parameters."""

import re
from typing import Any
from urllib.parse import urlparse


def validate_table_name(table: str) -> str | None:
    """Validate a database table name. Returns error message or None."""
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table):
        return f"Invalid table name: {table}"
    return None


def validate_where_clause(where: str) -> str | None:
    """Validate a simple WHERE clause. Returns error message or None.

    Only allows simple conditions: column=value, column>value, column<value,
    column LIKE 'value'. No subqueries or complex expressions.
    """
    pattern = r"^[a-zA-Z_][a-zA-Z0-9_]*\s*(=|!=|>|<|>=|<=|LIKE)\s*('[^']*'|[\w.]+)$"
    if not re.match(pattern, where.strip()):
        return f"Invalid WHERE clause: {where}"
    return None


def validate_url(url: str, allowed_schemes: tuple[str, ...] = ('http', 'https')) -> str | None:
    """Validate a URL. Returns error message or None."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in allowed_schemes:
            return f"Invalid URL scheme: {parsed.scheme}"
        if not parsed.netloc:
            return f"Invalid URL (no host): {url}"
        return None
    except Exception:
        return f"Invalid URL: {url}"


def validate_identifier(name: str, field: str = "identifier") -> str | None:
    """Validate a machine name / identifier. Returns error message or None."""
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
        return f"Invalid {field}: {name}"
    return None


def validate_email(email: str) -> str | None:
    """Validate an email address. Returns error message or None."""
    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        return f"Invalid email: {email}"
    return None


def validate_pagination(page_limit: int, page_offset: int) -> str | None:
    """Validate pagination parameters. Returns error message or None."""
    if not isinstance(page_limit, int) or page_limit < 1 or page_limit > 500:
        return "page_limit must be an integer between 1 and 500"
    if not isinstance(page_offset, int) or page_offset < 0:
        return "page_offset must be a non-negative integer"
    return None


def validate_path_prefix(path: str, allowed_prefixes: tuple[str, ...]) -> str | None:
    """Validate that a path starts with an allowed prefix. Returns error message or None."""
    if not any(path.startswith(p) for p in allowed_prefixes):
        return f"Invalid path. Must start with one of: {allowed_prefixes}"
    return None


def sanitize_string(value: str, max_length: int = 255) -> str | None:
    """Sanitize a string input. Returns error message or None."""
    if not isinstance(value, str):
        return f"Expected string, got {type(value).__name__}"
    if len(value) > max_length:
        return f"String exceeds maximum length of {max_length}"
    # Check for dangerous characters
    dangerous = [';', '|', '&', '$', '`', '\\']
    for char in dangerous:
        if char in value:
            return f"String contains forbidden character: {char!r}"
    return None


def validate_integer(value: Any, min_val: int, max_val: int, field: str = "value") -> str | None:
    """Validate an integer within a range. Returns error message or None."""
    if not isinstance(value, int):
        return f"{field} must be an integer, got {type(value).__name__}"
    if value < min_val or value > max_val:
        return f"{field} must be between {min_val} and {max_val}"
    return None
