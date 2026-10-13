# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability, please
report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, email security@drupal-mcp.example.com with:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will acknowledge receipt within 48 hours and aim to provide a fix or
mitigation within 7 days.

## Security Measures

This project implements the following security measures:

- Input validation on all user-provided parameters (SQL, shell, file paths)
- No shell interpolation — all subprocess calls use argument arrays
- Authentication required for HTTP transport endpoints
- OAuth 2.1 with per-session scopes for MCP HTTP transport
- Path traversal protection on file operations
- Subprocess timeouts to prevent hanging

## Dependency Security

- Dependencies are pinned with minimum versions in `pyproject.toml`
- Run `pip-audit` to check for known vulnerabilities
- Dependabot is enabled for automated dependency updates
