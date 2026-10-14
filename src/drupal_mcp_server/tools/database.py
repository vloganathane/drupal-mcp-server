"""Database query tools for Drupal."""

from typing import Any

from fastmcp import FastMCP

from ..validation import validate_single_select, validate_table_name, validate_where_clause
from ._utils import ensure_dict as _ensure_dict


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")

    @mcp.tool()
    async def db_query(query: str, args: list[str] | None = None) -> dict[str, Any]:
        """Execute a single read-only SELECT query on the Drupal database.

        One statement only, no comments, and no write or file-access clauses.
        """
        if not drush:
            return {"error": "Drush not available"}
        try:
            problem = validate_single_select(query)
            if problem:
                return {"error": problem}

            cmd_args = [query]
            if args:
                cmd_args.extend(args)

            result = await drush.run("sql:query", cmd_args)
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def db_tables() -> dict[str, Any]:
        """List all database tables."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            result = await drush.run("sql:query", ["SHOW TABLES"])
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def db_table_info(table: str) -> dict[str, Any]:
        """Get table schema information."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            problem = validate_table_name(table)
            if problem:
                return {"error": problem}
            result = await drush.run("sql:query", [f"DESCRIBE {table}"])
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def db_count(table: str, where: str | None = None) -> dict[str, Any]:
        """Count rows in a table."""
        if not drush:
            return {"error": "Drush not available"}
        try:
            problem = validate_table_name(table)
            if problem:
                return {"error": problem}
            query = f"SELECT COUNT(*) as count FROM {table}"
            if where:
                problem = validate_where_clause(where)
                if problem:
                    return {"error": problem}
                query += f" WHERE {where}"
            result = await drush.run("sql:query", [query])
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}
