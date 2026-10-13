# Drupal MCP Server

A Model Context Protocol (MCP) server for Drupal operations. Provides 35+ tools for site analysis, migration, content management, configuration, and DevOps operations.

## Quick Links

- [Installation](installation.md) — Get started in 5 minutes
- [Architecture](architecture.md) — How the server works internally
- [Contributing](CONTRIBUTING.md) — How to contribute code
- [Changelog](CHANGELOG.md) — What's changed recently

## Features at a Glance

| Category | Tools | Description |
|----------|-------|-------------|
| Content | 12 | CRUD for nodes, media, users, taxonomy, comments |
| Users | 8 | User management, roles, permissions |
| DevOps | 10 | DDEV/Lando, Drush, database, cron |
| Security | 6 | Audits, scanning, permission checks |
| Migration | 7 | D7 to D10 upgrade assistance |
| AI | 4 | Content analysis, field mapping, planning |
| Module Dev | 10 | Scaffolding for modules, plugins, forms |

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
