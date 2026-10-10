"""Unit tests for tool registration."""
from unittest.mock import MagicMock


def test_analysis_tools_register():
    from drupal_mcp_server.tools import analysis
    mcp = MagicMock()
    mcp.tool = lambda: lambda f: f
    
    analysis.register_tools(mcp)
    assert mcp.tool.call_count == 6


def test_content_tools_register():
    from drupal_mcp_server.tools import content
    mcp = MagicMock()
    mcp.tool = lambda: lambda f: f
    
    content.register_tools(mcp)
    assert mcp.tool.call_count == 7


def test_all_tool_modules_register():
    from drupal_mcp_server.tools import analysis, migration, content, config, devops, ai
    for module in [analysis, migration, content, config, devops, ai]:
        mcp = MagicMock()
        mcp.tool = lambda: lambda f: f
        module.register_tools(mcp)
