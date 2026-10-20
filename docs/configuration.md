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

These drive the **outbound** leg: the server POSTs
`grant_type=client_credentials` to `DRUPAL_OAUTH_TOKEN_URL` and sends the
resulting bearer to Drupal ([Architecture](architecture.md#auth-strategy-selection)).
The same `DRUPAL_OAUTH_CLIENT_ID` doubles as the HTTP-transport guard's
intent switch below — MCP-side tokens are issued and checked in-process,
not by this endpoint ([ADR 0005](adr/0005-oauth-token-validation.md)).

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
| `MCP_HOST` | `127.0.0.1` | HTTP bind host — loopback by default, see below |
| `MCP_PORT` | `8000` | HTTP bind port |
| `MCP_ALLOW_INSECURE_HTTP` | `false` | Permit an HTTP transport without OAuth (see below) |
| `MCP_READ_ONLY` | `false` | Expose only read-only tools — writes, file output and command execution are hidden (see below) |
| `MCP_RATE_LIMIT` | `0` | HTTP requests per minute per client, `0` disables (see below) |
| `MCP_SERVER_NAME` | `drupal-mcp-server` | Server name in MCP protocol |
| `MCP_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

### Serving over HTTP

The tool surface executes drush, composer and shell commands, so an HTTP
transport is not just an API — anyone who can reach the bind address can run
commands. Two defaults protect against that:

- **the server refuses to start** an `http`/`sse`/`streamable-http` transport
  unless `DRUPAL_OAUTH_CLIENT_ID` is set — the guard's deliberate-intent
  switch. Once bound, tokens are issued and checked **in-process** by
  FastMCP's bearer middleware, not delegated to Drupal
  ([ADR 0005](adr/0005-oauth-token-validation.md)); `CLIENT_SECRET` and
  `TOKEN_URL` belong to the outbound leg above. Set
  `MCP_ALLOW_INSECURE_HTTP=1` to override — that is a deliberate
  decision, not an oversight, and only sane on loopback behind a trusted network;
- **`MCP_HOST` binds `127.0.0.1`** rather than every interface. Serving to the
  network on purpose means setting `MCP_HOST` (and, typically, OAuth) on
  purpose.

Any client that can reach the port can register itself (RFC 7591) and
walk the PKCE flow to a token: the flow proves the caller speaks MCP's
OAuth dialect, not who the user is — which is why the loopback default
is doing real work. See [ADR 0005](adr/0005-oauth-token-validation.md).

Two further controls narrow what an authenticated socket can do, both
opt-in:

- **`MCP_READ_ONLY=1`** exposes only tools whose names read as queries
  (`list_`/`get_`/`find_`/`search_` prefixes, `_list`/`_get`/`_audit`/
  `_scan`/... suffixes, plus a vetted extras list) — 185 of the 414
  tools. Everything that writes to the site, writes files, or executes
  drush/composer/shell commands is **not registered at all**, so
  `tools/list` cannot advertise it and a call by the name fails as an
  unknown tool. The classifier is deliberately fail-closed: a future
  tool stays hidden until its name reads as a query, because a wrong
  allow is a write while a wrong deny is an operator flipping the flag.
  A single exception, `search_api_*`, is pinned the other way — the
  `search_` prefix heads a mutation family (create/reindex/clear/
  enable), so those eight names are denied explicitly while the
  family's readers pass on their own suffixes.
- **`MCP_RATE_LIMIT=120`** puts a token bucket of 120 requests/minute
  on every HTTP route — MCP endpoints, custom routes, and the OAuth
  token endpoint alike — answering `429` with `Retry-After` past the
  budget, and reporting `X-RateLimit-Limit`/`X-RateLimit-Remaining` on
  the way through. The bucket is keyed by bearer token when the request
  carries one (a credential being guessed burns its own budget, not the
  shared address of every client behind it), else by client IP.
  `0` — the default — disables it.

### Delegating OAuth to Drupal (multi-user)

The in-process authorization server proves a caller speaks OAuth, not
who the user is. A multi-user networked deployment that needs
Drupal-side identity opts into proxy delegation instead
([ADR 0005](adr/0005-oauth-token-validation.md)):

```bash
DRUPAL_OAUTH_DELEGATE=1
DRUPAL_OAUTH_CLIENT_ID=<client registered in Drupal's simple_oauth>
DRUPAL_OAUTH_CLIENT_SECRET=<its secret>
DRUPAL_OAUTH_TOKEN_URL=https://site.example/oauth/token
```

MCP clients keep the standard flow against this server — discovery,
dynamic registration, PKCE — while authorize/token requests are
forwarded to Drupal's simple_oauth server, and every presented token is
validated per request: locally via JWKS (`…/oauth/jwks`, derived from
the token URL by convention) so validation costs no network hop, or by
RFC 7662 introspection when `DRUPAL_OAUTH_INTROSPECTION_URL` is set
(a hop per cold token, cached). Optional knobs:
`DRUPAL_OAUTH_AUTH_ENDPOINT` / `DRUPAL_OAUTH_JWKS_URI` override the
derived endpoints, `DRUPAL_OAUTH_AUDIENCE` pins the audience claim,
`DRUPAL_OAUTH_REQUIRED_SCOPES` sets a scope minimum (empty accepts any
valid token — tool authorization is whatever Drupal put in it), and
`MCP_BASE_URL` gives the public URL for redirects when it differs from
`http://{MCP_HOST}:{MCP_PORT}`. Missing upstream credentials refuse to
start with the reason, as the unauthenticated-socket guard does.

The delegated flow is pinned offline against generated keys and a stub
upstream (signature, expiry, audience, scope and revocation failures
all answer None); the live simple_oauth round trip is not yet
exercised — recorded as a live gap, like the outbound
client-credentials leg.

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
