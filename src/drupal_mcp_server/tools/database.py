"""Database query tools for Drupal."""

from typing import Any

from fastmcp import FastMCP

from ._utils import ensure_dict as _ensure_dict


def register_tools(mcp: FastMCP, **deps: Any) -> None:
    drush = deps.get("drush_client")

    @mcp.tool()
    async def db_query(query: str, args: list[str] | None = None) -> dict[str, Any]:
        """Execute a SELECT query on the Drupal database.
        
        Only SELECT queries are allowed for safety.
        """
        if not drush:
            return {"error": "Drush not available"}
        try:
            # Validate it's a SELECT query
            query_stripped = query.strip().upper()
            if not query_stripped.startswith("SELECT"):
                return {"error": "Only SELECT queries are allowed for safety"}
            
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
            # Validate table name to prevent SQL injection
            import re
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table):
                return {"error": f"Invalid table name: {table}"}
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
            # Validate table name to prevent SQL injection
            import re
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table):
                return {"error": f"Invalid table name: {table}"}
            query = f"SELECT COUNT(*) as count FROM {table}"
            if where:
                # Basic WHERE clause validation — only allow simple conditions
                # Format: column=value, column>value, column<value, column LIKE 'value'
                if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]+\s*(=|!=|>|<|>=|<=|LIKE)\s*('[^']*'|[\w.]+)$", where.strip()):
                    return {"error": f"Invalid WHERE clause: {where}"}
                query += f" WHERE {where}"
            result = await drush.run("sql:query", [query])
            return _ensure_dict(result)
        except Exception as e:
            return {"error": str(e)}
