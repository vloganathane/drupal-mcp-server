# Architecture Overview

- **Server Core:** Built on FastMCP by Anthropic.
- **Config:** Pydantic Settings reads from `.env`.
- **Clients:** `httpx` async clients for JSON:API and GraphQL. Subprocess wrappers for Drush and DDEV.
- **AI Service:** Multi-provider interface wrapping Ollama (local default), OpenAI, Anthropic, and NVIDIA NIM REST endpoints.
- **Tools:** 35 functions mounted as MCP tools via `@mcp.tool()` decorators across 6 Python modules, passing clients via `deps` dictionary in the factory pattern.
