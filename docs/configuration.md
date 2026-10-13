# Configuration

All configuration is done via environment variables or a `.env` file.

## Authentication

### Basic Auth (Development)

```bash
DRUPAL_USERNAME=admin
DRUPAL_PASSWORD=secret
```

### OAuth2 (Production)

```bash
DRUPAL_OAUTH_CLIENT_ID=your-client-id
DRUPAL_OAUTH_CLIENT_SECRET=your-client-secret
DRUPAL_OAUTH_TOKEN_URL=https://yoursite.com/oauth/token
```

### Bearer Token

```bash
DRUPAL_API_TOKEN=your-pre-obtained-token
```

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

```bash
DRUSH_PATH=drush
DRUSH_ALIAS=@self
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
