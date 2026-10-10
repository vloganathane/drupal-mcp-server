"""Unit tests for tool modules."""
import pytest


def test_analysis_register():
    from drupal_mcp_server.tools import analysis
    assert hasattr(analysis, "register_tools")
