"""Reusable input validation for all tool parameters."""

import re
from typing import Any
from urllib.parse import urlparse


def validate_single_select(query: str) -> str | None:
    """Validate that `query` is one read-only SELECT. Returns an error or None.

    `db_query` used to guard with `startswith("SELECT")`, which any
    `SELECT 1; DROP TABLE x` satisfies. Run against a real database, such a
    query dropped the probe table, so the check tested the first word rather
    than what would execute.

    Rejects a second statement, DML/DDL keywords outside a string literal,
    and the clauses that turn a read into a write or a file access.
    """
    body = _strip_sql_literals(query)

    # Anything after a semicolon is a second statement. A single trailing
    # semicolon is harmless and common, so allow that one.
    if ";" in body.rstrip().rstrip(";"):
        return "Multiple SQL statements are not allowed; run one query at a time"

    # A comment can hide a second statement from the checks above.
    if re.search(r"(?<![-\w])--|/\*|\*/|#", body):
        return "SQL comments are not allowed"

    # LOAD_FILE and INTO OUTFILE are themselves functions/clauses of a single
    # SELECT, so the parenthesis exemption below must not apply to them: that
    # hole let `SELECT LOAD_FILE('/etc/passwd')` through.
    dangerous = re.search(
        r"\b(INTO\s+(OUT|DUMP)FILE|LOAD_FILE|LOAD\s+DATA)\b", body, re.IGNORECASE
    )
    if dangerous:
        return f"'{dangerous.group(1).upper()}' is not allowed in a SELECT query"

    # DML/DDL cannot be a statement here: the query must start with SELECT and
    # only one statement is allowed, so these are defence in depth. REPLACE is
    # exempt when followed by "(" because it is then the string function.
    forbidden = re.search(
        r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE|EXEC)\b"
        r"|\bREPLACE\b(?!\s*\()",
        body,
        re.IGNORECASE,
    )
    if forbidden:
        # group(0), not group(1): REPLACE matches in the second alternative
        # where group(1) never participates and is None.
        return f"'{forbidden.group(0).upper()}' is not allowed in a SELECT query"

    if not re.match(r"^\s*\(?\s*SELECT\b", query, re.IGNORECASE):
        return "Only SELECT queries are allowed for safety"
    return None


def _strip_sql_literals(sql: str) -> str:
    """Replace the contents of quoted strings with nothing.

    Checking for `;` or `DROP` without doing this would reject the legitimate
    `WHERE title = 'a; b'` while still missing nothing that matters, since a
    literal cannot contain a statement of its own.
    """
    out: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(sql):
        ch = sql[i]
        if quote:
            if ch == "\\" and i + 1 < len(sql):
                i += 2
                continue
            if ch == quote:
                # SQL escapes a quote by doubling it.
                if i + 1 < len(sql) and sql[i + 1] == quote:
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        if ch in "'\"`":
            quote = ch
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


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
