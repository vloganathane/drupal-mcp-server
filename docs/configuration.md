# Configuration

All configuration is done via environment variables or a `.env` file.

## Drupal Connection

| Variable | Default | Description |
|----------|---------|-------------|
| `DRUPAL_BASE_URL` | `http://localhost` | Base URL of the Drupal site |
| `DRUPAL_JSONAPI_PATH` | `/jsonapi` | JSON:API endpoint path |
| `DRUPAL_GRAPHQL_PATH` | `/graphql` | GraphQL endpoint path |
| `DRUPAL_VERIFY_SSL` | `true` | Set `false` for self-signed dev certificates (DDEV, Lando) |
| `DRUPAL_HTTP_TIMEOUT` | `60` | Timeout in seconds for one outbound HTTP request to Drupal |
| `DRUPAL_HTTP_RETRIES` | `2` | Extra attempts for **GET** requests on transient failures (timeout, connection reset, 502/503/504). Mutations are never retried: a timed-out POST may already have landed |

## Authentication

### Username and Password

```bash
DRUPAL_USERNAME=admin
DRUPAL_PASSWORD=secret
```

Drupal answers 403 on its write endpoints when only basic credentials are
sent, so the server first logs in to `/user/login`, reuses the session cookie,
and attaches the CSRF token that mutating JSON:API requests require. Basic
auth headers are still sent when a session cannot be established, so reads
keep working on sites that do not expose `/user/login`.

### OAuth2

```bash
DRUPAL_OAUTH_CLIENT_ID=your-client-id
DRUPAL_OAUTH_CLIENT_SECRET=your-client-secret
DRUPAL_OAUTH_TOKEN_URL=https://yoursite.com/oauth/token
```

### Bearer Token

```bash
DRUPAL_API_TOKEN=your-pre-obtained-token
```

Sent as `Authorization: Bearer <token>`, and used only when neither
`DRUPAL_OAUTH_TOKEN_URL` nor a username/password pair is configured.

## Server

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_TRANSPORT` | `stdio` | `stdio`, `http`, `sse`, `streamable-http` |
| `MCP_HOST` | `0.0.0.0` | HTTP bind host |
| `MCP_PORT` | `8000` | HTTP bind port |
| `MCP_SERVER_NAME` | `drupal-mcp-server` | Server name in MCP protocol |
| `MCP_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

## AI Providers

```bash
DEFAULT_AI_PROVIDER=ollama
AI_ENABLED=true
AI_TIMEOUT=60
AI_FALLBACK_TO_CORE=true
```

### Ollama (Local)

```bash
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
```

### OpenAI

```bash
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

### Anthropic

```bash
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-3-5-haiku-20241022
```

### NVIDIA NIM

```bash
NVIDIA_NIM_API_KEY=nvapi-...
NVIDIA_NIM_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_NIM_MODEL=nvidia/nemotron-3-ultra
```

## Drush

| Variable | Default | Description |
|----------|---------|-------------|
| `DRUSH_PATH` | `drush` | Command used to run Drush. May contain arguments |
| `DRUSH_ALIAS` | `@self` | Drush site alias |
| `DRUSH_TIMEOUT` | `120` | Timeout in seconds for one drush command. Not retried: drush commands mutate |

Container-based setups are supported by putting the wrapper in `DRUSH_PATH`
and starting the MCP server from the project directory, so the wrapper can
find its project:

```bash
# DDEV
DRUSH_PATH="ddev drush"
# Lando
DRUSH_PATH="lando drush"
```

## DDEV

```bash
DDEV_BINARY=ddev
```

## Full Example `.env`

```bash
# Drupal Connection
DRUPAL_BASE_URL=https://your-site.com
DRUPAL_USERNAME=admin
DRUPAL_PASSWORD=secret

# MCP Server
MCP_TRANSPORT=stdio
MCP_LOG_LEVEL=INFO

# AI Provider (Ollama)
DEFAULT_AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b

# Drush
DRUSH_PATH=drush
DRUSH_ALIAS=@self
```
