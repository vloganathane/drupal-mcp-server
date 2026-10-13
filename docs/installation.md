# Installation

## Prerequisites

- Python 3.11 or higher
- A Drupal 9/10/11 site with JSON:API enabled
- Drush (for DevOps tools)

## Install from PyPI

```bash
pip install drupal-mcp-server
```

## Install from Source

```bash
git clone https://github.com/your-org/drupal-mcp-server.git
cd drupal-mcp-server
pip install -e .
```

## Verify Installation

```bash
drupal-mcp --help
```

## Optional Dependencies

Install only the AI providers you need:

```bash
pip install drupal-mcp-server[openai]
pip install drupal-mcp-server[anthropic]
pip install drupal-mcp-server[all]
```

## Next Steps

- [Configuration](configuration.md) — Set up authentication and AI providers
- [Quickstart](quickstart.md) — Run your first tool call
