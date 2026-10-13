# Quickstart

Get up and running in 5 minutes.

## 1. Configure

Create a `.env` file:

```bash
DRUPAL_BASE_URL=https://your-drupal-site.com
DRUPAL_USERNAME=admin
DRUPAL_PASSWORD=your-secret
```

## 2. Run the Server

```bash
drupal-mcp
```

The server starts on stdio transport by default.

## 3. Connect a Client

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "drupal": {
      "command": "drupal-mcp",
      "env": {
        "DRUPAL_BASE_URL": "https://your-drupal-site.com",
        "DRUPAL_USERNAME": "admin",
        "DRUPAL_PASSWORD": "your-secret"
      }
    }
  }
}
```

### Custom MCP Client

```python
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    server_params = StdioServerParameters(
        command="drupal-mcp",
        env={"DRUPAL_BASE_URL": "https://your-drupal-site.com"}
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("query_nodes", {"bundle": "article"})
            print(result)

asyncio.run(main())
```

## 4. Call Your First Tool

```python
# List all article nodes
result = await query_nodes(bundle="article", page_limit=5)
for node in result["data"]:
    print(f"  - {node['attributes']['title']}")

# Create a new node
result = await create_node("article", {"title": "Hello World"})
print(f"Created node: {result['data']['id']}")
```

## Next Steps

- [Configuration](configuration.md) — Full configuration reference
- [Tools](tools/index.md) — Browse all available tools
