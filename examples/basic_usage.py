#!/usr/bin/env python3
"""Basic usage examples for Drupal MCP Server tools."""

import asyncio
from drupal_mcp_server.server import create_server


async def example_analyze_site():
    """Example: Analyze a Drupal 9 site for deprecated APIs."""
    mcp = create_server()
    # In practice, tools are invoked via MCP protocol
    # This shows the conceptual flow
    print("=== Analyzing Drupal 9 Site ===")
    # Tool would be called via: analyze_d9_site(site_url="https://example.com", check_deprecated=True)


async def example_inventory_content():
    """Example: List all content types on a site."""
    print("=== Inventory Content Types ===")
    # Tool: inventory_content_types(site_url="https://example.com", include_field_details=True)


async def example_bulk_update():
    """Example: Bulk update nodes using AI."""
    print("=== AI-Powered Bulk Update ===")
    # Tool: bulk_update_nodes_ai(
    #     content_type="article",
    #     field="body",
    #     transformation="Fix grammar and spelling",
    #     ai_provider="ollama"
    # )


async def example_drush_command():
    """Example: Run Drush commands."""
    print("=== Execute Drush Command ===")
    # Tool: drush_command(command="cache:rebuild")
    # Tool: drush_command(command="pm-list", args=["--status=enabled"])


async def example_ddev_workflow():
    """Example: DDEV local development workflow."""
    print("=== DDEV Workflow ===")
    # Tool: ddev_start(project_path="/path/to/drupal")
    # Tool: backup_database(backup_path="/tmp/backup.sql")
    # Tool: ddev_exec(command="drush cr")


if __name__ == "__main__":
    print("Drupal MCP Server - Usage Examples")
    print("=" * 50)
    asyncio.run(example_analyze_site())
    asyncio.run(example_inventory_content())
    asyncio.run(example_bulk_update())
    asyncio.run(example_drush_command())
    asyncio.run(example_ddev_workflow())
