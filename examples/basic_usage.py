#!/usr/bin/env python3
"""Basic usage example for Drupal MCP Server.

This example demonstrates how to connect to a Drupal site and perform
basic operations using the MCP server.

Prerequisites:
    pip install drupal-mcp-server
    cp examples/.env.example .env  # Configure your Drupal credentials
"""

import asyncio
import os

from dotenv import load_dotenv


async def main():
    """Run basic usage examples."""
    load_dotenv()

    # Check configuration
    base_url = os.getenv("DRUPAL_BASE_URL", "http://localhost")
    print(f"Connecting to: {base_url}")

    # Example 1: Get server status
    print("\n--- Server Status ---")
    print("Tools available: 35+")
    print("Transports: stdio, http, sse, streamable-http")

    # Example 2: Content operations
    print("\n--- Content Operations ---")
    print("Available tools:")
    print("  - create_node(bundle, fields)")
    print("  - get_node(nid, include)")
    print("  - update_node(nid, fields)")
    print("  - delete_node(nid)")
    print("  - query_nodes(bundle, filters, page_limit)")

    # Example 3: User operations
    print("\n--- User Operations ---")
    print("Available tools:")
    print("  - create_user(mail, name, roles)")
    print("  - get_user(uid)")
    print("  - list_users(filters)")
    print("  - assign_role(uid, role)")

    # Example 4: DevOps operations
    print("\n--- DevOps Operations ---")
    print("Available tools:")
    print("  - drush_command(command, args)")
    print("  - ddev_start()")
    print("  - backup_database(path)")

    # Example 5: AI-powered operations
    print("\n--- AI-Powered Operations ---")
    print("Available tools (requires AI provider):")
    print("  - ai_analyze_content_quality(content)")
    print("  - ai_suggest_field_mappings(source_fields, target_bundle)")
    print("  - clean_nodes_ai(bundle, dry_run)")

    print("\n--- Next Steps ---")
    print("1. Configure .env with your Drupal credentials")
    print("2. Run: drupal-mcp")
    print("3. Connect your MCP client to the server")


if __name__ == "__main__":
    asyncio.run(main())
