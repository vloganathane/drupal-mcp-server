# Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        MCP Client                                │
│              (Claude Desktop, Cursor, Custom)                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │ MCP Protocol (stdio / HTTP / SSE)
┌──────────────────────────▼──────────────────────────────────────┐
│                    Drupal MCP Server                             │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────────┐  │
│  │   Auth      │  │   FastMCP    │  │   Custom Routes       │  │
│  │  Manager    │  │   Engine     │  │  (/mcp/session/*)     │  │
│  └──────┬──────┘  └──────┬───────┘  └───────────┬───────────┘  │
│         │                │                       │              │
│  ┌──────▼──────┐  ┌──────▼───────┐  ┌───────────▼───────────┐  │
│  │  OAuth 2.1  │  │    Tool      │  │   Session Manager     │  │
│  │  Provider   │  │  Registry    │  │   (per-session scopes)│  │
│  └─────────────┘  └──────┬───────┘  └───────────────────────┘  │
│                          │                                       │
│  ┌───────────────────────▼───────────────────────────────────┐  │
│  │                    Service Layer                          │  │
│  │  ┌──────────┐  ┌──────────────┐  ┌────────────────────┐  │  │
│  │  │   AI     │  │   Migration  │  │   Site Manager     │  │  │
│  │  │ Service  │  │   Service    │  │   (DDEV/Lando)     │  │  │
│  │  └──────────┘  └──────────────┘  └────────────────────┘  │  │
│  └───────────────────────┬───────────────────────────────────┘  │
│                          │                                       │
│  ┌───────────────────────▼───────────────────────────────────┐  │
│  │                    Client Layer                           │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────────────┐ │  │
│  │  │JSON:API  │  │ GraphQL  │  │       Drush              │ │  │
│  │  │ Client   │  │ Client   │  │       Client             │ │  │
│  │  └────┬─────┘  └────┬─────┘  └────────────┬─────────────┘ │  │
│  └───────┼──────────────┼────────────────────┼───────────────┘  │
└──────────┼──────────────┼────────────────────┼──────────────────┘
           │              │                    │
           ▼              ▼                    ▼
    ┌─────────────┐ ┌─────────────┐    ┌─────────────┐
    │  Drupal     │ │  Drupal     │    │  Drupal     │
    │  JSON:API   │ │  GraphQL    │    │  (Drush)    │
    └─────────────┘ └─────────────┘    └─────────────┘
```

## Data Flow

### Tool Call Request

1. **MCP Client** sends a JSON-RPC 2.0 request via configured transport
2. **FastMCP Engine** routes the request to the appropriate tool function
3. **Auth Manager** injects authentication headers based on configured strategy
4. **Tool Function** validates input, calls service/client, returns result
5. **Response** is serialized as JSON-RPC 2.0 result or error

### JSON:API Request Flow

```
Tool Function → JSONAPIClient.get() → httpx.AsyncClient → Drupal JSON:API
                                                              ↓
Tool Function ← JSONAPIClient.get() ← httpx.Response ← Drupal JSON:API
```

### Drush Command Flow

```
Tool Function → DrushClient.run() → asyncio.subprocess_exec → Drush
                                                              ↓
Tool Function ← DrushClient.run() ← stdout/stderr ← Drush
```

## Authentication

### Auth Strategy Selection

The `AuthManager` selects authentication based on environment variables:

1. **Basic Auth** (`DRUPAL_USERNAME` + `DRUPAL_PASSWORD`)
   - Base64-encoded credentials in `Authorization: Basic` header
   - Simplest, suitable for development

2. **OAuth2 Client Credentials** (`DRUPAL_OAUTH_TOKEN_URL`)
   - Fetches access token via `httpx.post()`
   - Sends `Authorization: Bearer <token>` header
   - Token refresh handled by OAuth provider

3. **Bearer Token** (`DRUPAL_API_TOKEN`)
   - Pre-obtained token sent directly
   - Suitable for external token management

### HTTP Transport OAuth

For HTTP/SSE transports, the `DrupalOAuthProvider` implements OAuth 2.1:

- Client registration
- Authorization code flow
- Token exchange and refresh
- Per-session scope management
- WWW-Authenticate challenge

## Tool Registration

### Module Structure

Each tool module follows the same pattern:

```python
# src/drupal_mcp_server/tools/my_module.py
def register_tools(mcp: FastMCP, **deps: Any) -> None:
    jsonapi = deps.get("jsonapi_client")

    @mcp.tool()
    async def my_tool(param: str) -> dict[str, Any]:
        """Tool description."""
        result = await jsonapi.get_resource(param)
        return ensure_dict(result)
```

### Registration Flow

1. `create_server()` instantiates all clients and services
2. Each tool module's `register_tools()` is called with dependencies
3. Tools are registered with FastMCP using the `@mcp.tool()` decorator
4. FastMCP automatically generates JSON schemas from type hints

## Error Handling

### Exception Hierarchy

```
DrupalMCPError (base)
├── AuthenticationError — Invalid credentials
├── AuthorizationError — Insufficient permissions
├── ConfigurationError — Invalid/missing config
├── ClientError — 4xx responses
│   ├── NotFoundError — 404
│   └── ValidationError — 422
├── ServerError — 5xx responses
├── AIProviderError — AI service failure
├── MigrationError — Migration operation failure
└── DDEVError — DDEV operation failure
```

### Error Response Format

All tools return errors in a standardized format:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid table name: users; DROP TABLE",
    "status_code": 400
  }
}
```

### Error Recovery

- **AI failures** — Falls back to core tools if `AI_FALLBACK_TO_CORE=true`
- **Network timeouts** — HTTP client has 60s timeout, Drush has 120s
- **Auth failures** — Returns authentication error, client should re-authenticate
- **Rate limiting** — Returns 429 with Retry-After header

## Configuration

### Settings Loading

`pydantic-settings` loads from (in priority order):

1. Environment variables
2. `.env` file
3. Default values

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DRUPAL_BASE_URL` | Yes | `http://localhost` | Drupal site URL |
| `DRUPAL_USERNAME` | No | — | Basic auth username |
| `DRUPAL_PASSWORD` | No | — | Basic auth password |
| `MCP_TRANSPORT` | No | `stdio` | Transport type |
| `MCP_HOST` | No | `0.0.0.0` | HTTP bind host |
| `MCP_PORT` | No | `8000` | HTTP bind port |
| `DEFAULT_AI_PROVIDER` | No | `ollama` | AI provider |
| `AI_ENABLED` | No | `true` | Enable AI tools |
| `AI_TIMEOUT` | No | `60` | AI request timeout |

## Security Considerations

### Input Validation

- SQL queries validated against injection patterns
- File paths validated against traversal
- URLs validated for scheme and structure
- Table names validated with regex
- Queue names validated as identifiers

### Subprocess Safety

- No shell interpolation — all commands use argument arrays
- Timeout on all subprocess calls (120s)
- Output captured separately (stdout/stderr)

### Authentication

- No credentials in logs
- OAuth tokens stored in memory only
- Per-session scope isolation
