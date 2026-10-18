# Migration & Upgrade Guide

## Live migration test harnesses

DDEV-based live test scripts are included. They spin up throwaway Drupal sites in `/tmp` (not inside the repo) and are meant for local verification, not CI.

### JSON:API engine smoke test (D10 source → D11 target)
```bash
scripts/live-migration-d9d11.sh up      # provisions both sites, seeds source data, writes .env.d9d11
venv/bin/python scripts/live-migration-d9d11-run.py
scripts/live-migration-d9d11.sh down    # deletes both DDEV projects
```

The script enables `jsonapi` + `basic_auth` on both sites, turns off JSON:API read-only mode on the target, and writes source/target credentials to `.env.d9d11` (gitignored). The runner walks the full engine path: analyze → plan → dry run → live run → reconcile, and asserts source/target counts match.

### D7 to D11 legacy DB migration
```bash
scripts/live-migration-d7d11.sh up        # provisions both sites, seeds source data, writes .env.d7d11
scripts/live-migration-d7d11.sh migrate   # wires the target's 'migrate' DB connection, imports, verifies
scripts/live-migration-d7d11.sh down      # deletes both DDEV projects
```

The D7 harness uses the standard Drupal Migrate model, where the target reads the D7 database directly (D7 predates JSON:API). `migrate` is idempotent: it points core's `d7_*` sources at the source database via `$databases['migrate']`, runs the dependency-ordered imports (`d7_filter_format` → `d7_user_role` → `d7_user` → `d7_node_type` → `d7_node:article` → `d7_taxonomy_vocabulary` → `d7_taxonomy_term:departures`), and exits non-zero unless every one of them is Idle at full import, then prints the migrated article, body, author, and term for eyeball verification. The D9/D11 harness exercises the MCP JSON:API migration engine.

## End-to-end migration engine

The server supports persisted migration plans and wave-based imports.

Recommended flow:

1. `analyze_source_site(source_url=..., resource_type=..., username=..., password=...)`
2. `create_migration_plan(...)`
3. `run_migration(migration_id, entity_types=[...], dry_run=true)`
4. Review the returned per-wave results and `migration_status(...)`
5. `run_migration(migration_id, dry_run=false)`
6. `reconcile_migration_counts(migration_id, [...])`

Supported first-class orchestration today:
- Users, taxonomy, nodes/articles, media, and any other JSON:API resource type through `run_migration_wave`
- Idempotent create/update by tracked legacy IDs — re-running a wave updates tracked records instead of duplicating them
- Source-side authentication (`username`/`password` in the plan's `source` block, or per call), needed because JSON:API field access hides attributes (user name/mail, for example) from anonymous requests
- JSON:API filters per resource type (`source.filters`) to exclude records the target should not receive — the anonymous user, staged content, and so on
- Relationship UUID remapping: references to records migrated earlier in the run are rewritten to their new target UUIDs
- Schema-drift tolerance: bundle pointers and revision bookkeeping are dropped, computed sub-fields (`body.processed`, `body.summary`) are stripped, and any attribute or relationship a target rejects by name is dropped and the record retried (see `dropped_fields` in `migration_status`)
- Ordered waves with per-record error reporting; a failed wave stops the run by default (`continue_on_error=true` overrides)
- Source pagination, record counting, and target-side persistence of migration state

`reconcile_migration_counts` compares the recorded source counts against live target counts (JSON:API exposes no total-count metadata, so both sides are counted by walking the collection).

Remaining specialized work usually includes bespoke field-transform and content-block migration rules for a particular site.

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
MCP_HOST=127.0.0.1
MCP_PORT=8000
# HTTP transports refuse to start without OAuth; either configure
# DRUPAL_OAUTH_CLIENT_ID/CLIENT_SECRET/TOKEN_URL or opt in explicitly:
MCP_ALLOW_INSECURE_HTTP=1
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
2. Set `MCP_HOST` and `MCP_PORT`; configure OAuth or
   `MCP_ALLOW_INSECURE_HTTP=1`, or the server refuses to bind
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
