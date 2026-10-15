#!/usr/bin/env python3
"""Content workflow example for Drupal MCP Server.

Demonstrates a complete content creation workflow:
1. Create a node
2. Upload media
3. Set URL alias
4. Verify content

This is a documentation example — it shows the tool calls you would
make from an MCP client. Actual execution requires a running server.
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
    print(json.dumps(response, indent=2, default=str)[:500])


async def content_workflow():
    """Demonstrate content creation workflow."""
    load_dotenv()

    print("=== Content Creation Workflow ===\n")

    # Step 1: Create a node
    print_tool_call("create_node", {
        "bundle": "article",
        "fields": {
            "title": "My First Article",
            "body": {
                "value": "<p>This is the article content.</p>",
                "format": "basic_html"
            },
            "status": True
        }
    })
    print_response({
        "data": {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "type": "node--article",
            "attributes": {"title": "My First Article", "status": True}
        }
    })

    # Step 2: Upload media
    print_tool_call("upload_media", {
        "file_path": "/path/to/image.jpg",
        "media_type": "image",
        "alt": "Article header image",
        "title": "Header Image"
    })
    print_response({
        "data": {
            "id": "660e8400-e29b-41d4-a716-446655440001",
            "type": "media--image",
            "attributes": {"name": "image.jpg"}
        }
    })

    # Step 3: Generate URL alias
    print_tool_call("bulk_update_aliases", {
        "bundle": "article",
        "action": "generate"
    })
    print_response({"returncode": 0, "output": {"processed": 1}})

    # Step 4: Verify content
    print_tool_call("get_node", {
        "nid": "550e8400-e29b-41d4-a716-446655440000"
    })
    print_response({
        "data": {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "type": "node--article",
            "attributes": {"title": "My First Article", "status": True}
        }
    })

    print("\n=== Workflow Complete ===")
    print("Article created, media uploaded, alias generated, content verified.")


if __name__ == "__main__":
    asyncio.run(content_workflow())
