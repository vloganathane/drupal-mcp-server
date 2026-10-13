# ADR 0004: Support HTTP Transport with OAuth 2.1

## Status
Accepted

## Date
2026-10-13

## Context

The server needs to support remote deployments where stdio is not available:
- Web-based MCP clients
- Remote Drupal instances
- Multi-user access with different permission levels

## Decision

Use FastMCP's HTTP transport with a custom `DrupalOAuthProvider` implementing OAuth 2.1.

## Consequences

### Positive
- Remote access without SSH tunneling
- Per-session scope isolation (read, write, admin, migrate, devops, ai, security)
- Standard OAuth 2.1 flow — works with any OAuth client
- Custom routes for session management

### Negative
- More complex deployment (needs HTTPS in production)
- OAuth token management overhead
- Session state stored in memory (not persistent across restarts)

## Alternatives Considered

- **stdio only** — Simplest but limits use cases
- **SSE without auth** — Insecure for remote access
- **API key auth** — Simpler but less granular than OAuth scopes
