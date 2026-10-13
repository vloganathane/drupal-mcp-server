# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security

- Fix command injection vulnerabilities in code audit and security audit tools
- Fix SQL injection in database query tools
- Fix path traversal in media upload tool
- Add input validation for URLs, queue names, and file paths
- Add authentication check to /mcp/tools/list endpoint

### Added

- Add Lando support to SiteManager
- Add subprocess timeout to DrushClient
- Add OAuth token fetching to AuthManager
- Create shared tools/_utils.py with ensure_dict, validate_pagination, build_pagination_params
- Add pagination validation to list tools
- Add input validation to accessibility and performance tools
- Add LICENSE, CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md
- Add GitHub issue and PR templates

### Changed

- Extract _ensure_dict from 35+ tool modules into shared utility
- Remove duplicate service implementations (ai.py, migration.py, site.py)
- Clean up unused imports across all tool modules
- Update ARTIFACT.md to reflect actual project state

### Removed

- Remove dead register_all_tools function from tools/__init__.py
- Remove duplicate _find_tool_path definition in security_audit.py

## [0.1.0] - 2026-10-13

### Added

- Initial release with 35+ MCP tools across all major Drupal categories
- FastMCP server with stdio and HTTP transports
- JSON:API and GraphQL clients with authentication
- Drush command execution via subprocess
- Multi-provider AI support (Ollama, OpenAI, Anthropic, NVIDIA NIM)
- Content management, user management, taxonomy, views, paragraphs tools
- DevOps tools for DDEV/Lando, Composer, database queries
- Migration tools for D7 to D10 upgrades
- Security audit and code quality tools
