# Drupal MCP Server

A Model Context Protocol (MCP) server for Drupal operations. Provides 404 tools across 40 modules for site analysis, migration, content management, configuration, commerce, headless, DevOps, security, and more.

## Quick Links

- [Installation](installation.md) — Get started in 5 minutes
- [Architecture](architecture.md) — How the server works internally
- [Contributing](CONTRIBUTING.md) — How to contribute code
- [Changelog](CHANGELOG.md) — What's changed recently

## Features at a Glance

A sample of the catalog — the full list of all 404 tools lives in the
[README's Tools section](https://github.com/vloganathane/drupal-mcp-server#tools-404-total).

| Category | Tools | Description |
|----------|-------|-------------|
| Content | 14 | CRUD for nodes, media, users, taxonomy, comments |
| Users | 12 | User management, roles, permissions |
| DevOps | 20 | DDEV/Lando, Drush, database, cron |
| Security Audit | 8 | Audits, scanning, permission checks |
| Migration | 17 | Plans, batch import, reconciliation between Drupal sites |
| AI | 4 | Content analysis, field mapping, planning |
| Module Dev | 12 | Scaffolding for modules, plugins, forms |
| Codebase | 12 | Local codebase index, hook search, unused module detection |
| Status | 4 | Status report, pending updates, health diagnostics |
| Exports | 4 | CSV/Excel inventories of content, users, media, taxonomy |

## Example: Create a Node

```python
result = await create_node("article", {
    "title": "My First Article",
    "body": {"value": "<p>Hello World</p>", "format": "basic_html"}
})
print(result["data"]["id"])  # UUID of created node
```

## Example: Run a Drush Command

```python
result = await drush_command("status")
print(result["data"]["drupal-version"])
```
