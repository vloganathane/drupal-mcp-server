#!/usr/bin/env python3
"""Migration workflow example for Drupal MCP Server.

Demonstrates a D7 to D10 migration workflow:
1. Analyze source site
2. Generate migration config
3. Create migration module
4. Test migration
5. Run full migration

This is a documentation example — it shows the tool calls you would
make from an MCP client. Actual execution requires a running server
with access to both D7 source and D10 destination.
"""

import asyncio
import json

from dotenv import load_dotenv


def print_tool_call(tool_name: str, params: dict):
    """Pretty print a tool call."""
    print(f"\n>>> {tool_name}")
    print(json.dumps(params, indent=2))


def print_response(response: dict):
    """Pretty print a tool response."""
    print("<<< Response:")
    print(json.dumps(response, indent=2, default=str)[:800])


async def migration_workflow():
    """Demonstrate D7 to D10 migration workflow."""
    load_dotenv()

    print("=== D7 to D10 Migration Workflow ===\n")

    # Step 1: Analyze D7 site
    print_tool_call("analyze_d7_site", {
        "site_url": "https://d7.example.com",
        "include_modules": True,
        "include_content": True
    })
    print_response({
        "drupal_version": "7.x",
        "ready_for_d10": False,
        "blockers": 3,
        "warnings": 12,
        "module_migration_plan": [
            {"module": "views", "d10_equivalent": "Drupal core (Views)", "migration_complexity": "low"},
            {"module": "ctools", "d10_equivalent": "Drupal core (Plugin API)", "migration_complexity": "low"},
            {"module": "rules", "d10_equivalent": "Rules (D9+) or Event Subscribers", "migration_complexity": "medium"}
        ]
    })

    # Step 2: Generate migration YAML
    print_tool_call("generate_migration_yaml", {
        "migration_type": "d7_node_to_d10_article",
        "source": {"plugin": "d7_node", "key": "default"},
        "destination": {"plugin": "entity:node", "default_bundle": "article"}
    })
    print_response({
        "yaml": "id: d7_node_to_d10_article\n...",
        "type": "d7_node_to_d10_article"
    })

    # Step 3: Generate migration module
    print_tool_call("generate_module_migration", {
        "module_name": "custom_migration",
        "source_version": "7",
        "target_version": "10"
    })
    print_response({
        "module_name": "custom_migration",
        "files_created": [
            "src/Plugin/migrate/source/custom_migration.php",
            "migrations/custom_migration.yml",
            "custom_migration.info.yml",
            "custom_migration.module"
        ]
    })

    # Step 4: Test migration with limited records
    print_tool_call("run_migration_test", {
        "migration_id": "d7_node_to_d10_article",
        "limit": 10
    })
    print_response({"returncode": 0, "data": {"imported": 10, "errors": 0}})

    # Step 5: Validate migration
    print_tool_call("validate_migration", {
        "migration_id": "d7_node_to_d10_article"
    })
    print_response({
        "returncode": 0,
        "status": {"imported": 100, "remaining": 500, "total": 600}
    })

    print("\n=== Migration Workflow Complete ===")
    print("D7 site analyzed, migration config created, module generated, test passed.")


if __name__ == "__main__":
    asyncio.run(migration_workflow())
