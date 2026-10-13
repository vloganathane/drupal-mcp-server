# Migration & Upgrade Guide

## Table of Contents

- [Upgrading from 0.1.x to 0.2.x](#upgrading-from-01x-to-02x)
- [Transport Migration](#transport-migration)
- [Configuration Changes](#configuration-changes)
- [Breaking Changes](#breaking-changes)
- [Deprecation Policy](#deprecation-policy)

---

## Upgrading from 0.1.x to 0.2.x

### Step 1: Update the package

```bash
pip install --upgrade drupal-mcp-server
```

### Step 2: Update your `.env` file

New required variables:

```bash
# Add if using HTTP transport
MCP_TRANSPORT=streamable-http
MCP_HOST=0.0.0.0
MCP_PORT=8000
```

### Step 3: Update your MCP client config

**Before (stdio only):**
```json
{
  "mcpServers": {
    "drupal": {
      "command": "drupal-mcp"
    }
  }
}
```

**After (HTTP transport):**
```json
{
  "mcpServers": {
    "drupal": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### Step 4: Verify

```bash
# Check server starts
drupal-mcp --help

# Test connection
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | drupal-mcp
```

---

## Transport Migration

### From stdio to HTTP

1. Set `MCP_TRANSPORT=streamable-http` in `.env`
2. Set `MCP_HOST` and `MCP_PORT`
3. Update client config to use `url` instead of `command`
4. Restart the server

### From HTTP to stdio

1. Remove `MCP_TRANSPORT` or set to `stdio`
2. Update client config to use `command` instead of `url`
3. Restart the server

### Transport Comparison

| Feature | stdio | HTTP | SSE | Streamable HTTP |
|---------|-------|------|-----|-----------------|
| Local desktop | Yes | No | No | No |
| Remote access | No | Yes | Yes | Yes |
| OAuth 2.1 | No | Yes | Yes | Yes |
| Session management | No | Yes | Yes | Yes |
| Easiest setup | Yes | No | No | No |

---

## Configuration Changes

### Renamed Variables

| Old Name | New Name | Notes |
|----------|----------|-------|
| `DRUPAL_API_URL` | `DRUPAL_BASE_URL` | More consistent naming |
| `DRUSH` | `DRUSH_PATH` | Clearer purpose |

### Removed Variables

| Variable | Reason |
|----------|--------|
| `MCP_DEBUG` | Use `MCP_LOG_LEVEL=DEBUG` instead |

### New Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_LOG_LEVEL` | `INFO` | Logging verbosity |
| `AI_FALLBACK_TO_CORE` | `true` | Fallback if AI fails |
| `AI_TIMEOUT` | `60` | AI request timeout |

---

## Breaking Changes

### 0.2.0

- **Removed**: `register_all_tools()` function from `tools/__init__.py`
- **Changed**: `_ensure_dict` moved to `tools/_utils.py` (import path changed)
- **Changed**: Service imports consolidated — use `from drupal_mcp_server.services import AIService`

### 0.1.0

- Initial release — no breaking changes

---

## Deprecation Policy

- Deprecated features are announced in the changelog one release before removal
- Deprecated features emit `DeprecationWarning` when used
- Minimum 2 releases between deprecation and removal
- Security fixes may bypass deprecation cycle
