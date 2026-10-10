"""Tool modules for Drupal MCP Server."""
from . import analysis, migration, content, config, devops, ai

def register_all_tools(mcp, **deps):
    """Register all tools across all categories."""
    for module in [analysis, migration, content, config, devops, ai]:
        module.register_tools(mcp, **deps)
