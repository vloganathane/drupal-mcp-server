# Quickstart

Get the server running against a Drupal site and make your first tool call.

## 1. Install

```bash
pip install drupal-mcp-server
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv pip install drupal-mcp-server
```

## 2. Configure

Copy the example environment file:

```bash
cp examples/.env.example .env
```

The only required values are the site URL and a credential pair:

```bash
DRUPAL_BASE_URL=https://your-drupal-site.com
DRUPAL_USERNAME=admin
DRUPAL_PASSWORD=secret
```

The server logs in to `/user/login` and reuses the session cookie plus the CSRF
token that Drupal's mutating JSON:API endpoints require — basic auth alone is
rejected with 403 on writes. If you're pointing at a local DDEV or Lando site
with a self-signed certificate, also set:

```bash
DRUPAL_VERIFY_SSL=false
```

See [Configuration](configuration.md) for OAuth, bearer-token, Drush, AI
provider, and transport options.

## 3. Run

Start the server over stdio (the default, used by desktop MCP clients):

```bash
drupal-mcp
```

To confirm it is alive, send a `tools/list` request:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | drupal-mcp
```

## 4. Connect an MCP client

For Claude Desktop, add the server to
`~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "drupal": {
      "command": "drupal-mcp",
      "env": {
        "DRUPAL_BASE_URL": "https://your-drupal-site.com",
        "DRUPAL_USERNAME": "admin",
        "DRUPAL_PASSWORD": "secret"
      }
    }
  }
}
```

Restart Claude Desktop; the Drupal tools appear in the tool picker.

## Next steps

- [Configuration](configuration.md) — authentication, Drush, AI providers, transport
- [Tools](tools/index.md) — the full tool catalog by category
- [Migration](migration.md) — end-to-end content migration between Drupal sites
