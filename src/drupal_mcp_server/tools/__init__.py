"""Tool modules for Drupal MCP Server."""

from typing import Any

from fastmcp import FastMCP

from . import ai, analysis, config, content, devops, migration


def register_all_tools(mcp: FastMCP, **deps: Any) -> None:
    """Register all tools across all categories."""
    for module in [analysis, migration, content, config, devops, ai]:
        module.register_tools(mcp, **deps)
