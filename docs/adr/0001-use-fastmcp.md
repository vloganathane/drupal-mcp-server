# ADR 0001: Use FastMCP Framework

## Status
Accepted

## Date
2026-10-13

## Context

We need a Python framework to build an MCP server that supports:
- Multiple transports (stdio, HTTP, SSE, Streamable HTTP)
- Tool registration with automatic schema generation
- OAuth 2.1 authentication for HTTP transport
- Type-safe tool parameters via Pydantic

## Decision

Use [FastMCP](https://github.com/jlowin/fastmcp) as the MCP server framework.

## Consequences

### Positive
- Automatic JSON Schema generation from Python type hints
- Built-in support for all MCP transports
- OAuth 2.1 provider integration out of the box
- Active maintenance and growing ecosystem
- Clean decorator-based tool registration

### Negative
- Additional dependency (though lightweight)
- Less control over low-level MCP protocol details
- Tied to FastMCP's release cycle

## Alternatives Considered

- **Raw MCP SDK** — More control but significantly more boilerplate
- **mcp-python** — Similar capabilities, smaller community
- **Custom implementation** — Full control but high maintenance cost
