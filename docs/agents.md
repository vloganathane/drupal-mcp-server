# Use with AI Coding Agents

Every MCP client needs the same three things: a command to spawn, arguments,
and the `DRUPAL_*` environment variables. Assembling those by hand differs
per client, so the server ships a self-installer that does it for you.

## One command

```bash
drupal-mcp install
```

With no arguments it:

1. **Detects** the MCP clients on this machine (Claude Code, Claude Desktop,
   Cursor, Codex CLI, OpenCode, Windsurf, Pi, Hermes Agent, OpenClaw) — by
   finding their CLI on `PATH` or a known config path.
2. **Gathers** `DRUPAL_*` settings from `./.env`, the process environment and
   any `--env` flags (precedence: dotenv < environment < flags).
3. **Writes** each client's config — preferring the client's own `mcp add`
   command when it has one, otherwise writing the documented file directly.

```
✓ claude-code: Added stdio MCP server drupal ... to local config
✓ codex: Added global MCP server 'drupal'.
✓ opencode: MCP server "drupal" added to ./opencode.json
```

## Useful options

| Option | Effect |
|--------|--------|
| `--client NAME` | Configure only this client (repeatable) |
| `--all` | Configure every supported client |
| `--list` | List supported client names |
| `--print` | Print the config/commands without writing anything |
| `--json` | Emit results as JSON (for scripted/agent-driven setup) |
| `--env KEY=VALUE` | Extra environment variable (repeatable) |
| `--dotenv PATH` | Env file to read (default `./.env` if present) |
| `--name NAME` | Server name inside the client config (default `drupal`) |
| `--command CMD` | Launch command override, e.g. `--command 'uvx drupal-mcp-server'` |
| `--scope local\|user\|project` | Claude Code configuration scope |
| `--global` | OpenCode: write the global config instead of the project one |

## What gets written where

| Client | Config | Mechanism |
|--------|--------|-----------|
| Claude Code | `claude mcp add` (or `./.mcp.json` with `--scope project`) | client CLI |
| Claude Desktop | `claude_desktop_config.json` (`mcpServers`) | direct write |
| Cursor | `~/.cursor/mcp.json` (`mcpServers`) | direct write |
| Codex CLI | `codex mcp add` (or `~/.codex/config.toml`) | client CLI |
| OpenCode | `opencode mcp add` (or `opencode.json` → `mcp.servers`) | client CLI |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` (`mcpServers`) | direct write |
| Pi | `pi mcp add` (or `~/.pi/agent/mcp.json`) | client CLI |
| Hermes Agent | `~/.hermes/config.yaml` (`mcp_servers`) | direct write |
| OpenClaw | `openclaw mcp add` | client CLI (required) |

The launch command is the absolute path to the `drupal-mcp` script when it is
on `PATH` (GUI clients like Claude Desktop launch servers with a sanitized
environment, so a bare name can fail there); otherwise `uvx drupal-mcp-server`
runs it straight from PyPI.

Existing configs are merged, never clobbered: other servers in the same file
survive, a server of the same name is replaced (so re-running is idempotent),
and a config that fails to parse is left untouched with an error instead of
being overwritten.

## Manual setup (copy-paste)

If you would rather wire it up yourself — every command below is verified
against the client's current CLI or docs:

=== "Claude Code"

    ```bash
    claude mcp add drupal \
      -e DRUPAL_BASE_URL=https://your-site.example \
      -e DRUPAL_USERNAME=admin \
      -e DRUPAL_PASSWORD=secret \
      -- drupal-mcp
    ```

=== "Claude Desktop"

    ```json
    {
      "mcpServers": {
        "drupal": {
          "command": "drupal-mcp",
          "args": [],
          "env": {
            "DRUPAL_BASE_URL": "https://your-site.example",
            "DRUPAL_USERNAME": "admin",
            "DRUPAL_PASSWORD": "secret"
          }
        }
      }
    }
    ```

=== "Cursor"

    ```json
    {
      "mcpServers": {
        "drupal": {
          "command": "drupal-mcp",
          "args": [],
          "env": {
            "DRUPAL_BASE_URL": "https://your-site.example",
            "DRUPAL_USERNAME": "admin",
            "DRUPAL_PASSWORD": "secret"
          }
        }
      }
    }
    ```

=== "Codex CLI"

    ```bash
    codex mcp add drupal \
      --env DRUPAL_BASE_URL=https://your-site.example \
      --env DRUPAL_USERNAME=admin \
      --env DRUPAL_PASSWORD=secret \
      -- drupal-mcp
    ```

=== "OpenCode"

    ```bash
    opencode mcp add drupal \
      --env DRUPAL_BASE_URL=https://your-site.example \
      --env DRUPAL_USERNAME=admin \
      --env DRUPAL_PASSWORD=secret \
      -- drupal-mcp
    ```

=== "Windsurf"

    ```json
    {
      "mcpServers": {
        "drupal": {
          "command": "drupal-mcp",
          "args": [],
          "env": {
            "DRUPAL_BASE_URL": "https://your-site.example",
            "DRUPAL_USERNAME": "admin",
            "DRUPAL_PASSWORD": "secret"
          }
        }
      }
    }
    ```

=== "Pi"

    ```bash
    pi mcp add drupal \
      --env DRUPAL_BASE_URL=https://your-site.example \
      --env DRUPAL_USERNAME=admin \
      --env DRUPAL_PASSWORD=secret \
      -- drupal-mcp
    ```

=== "Hermes Agent"

    ```yaml
    # ~/.hermes/config.yaml
    mcp_servers:
      drupal:
        command: "drupal-mcp"
        env:
          DRUPAL_BASE_URL: "https://your-site.example"
          DRUPAL_USERNAME: "admin"
          DRUPAL_PASSWORD: "secret"
    ```

=== "OpenClaw"

    ```bash
    openclaw mcp add drupal \
      --command drupal-mcp \
      --env DRUPAL_BASE_URL=https://your-site.example \
      --env DRUPAL_USERNAME=admin \
      --env DRUPAL_PASSWORD=secret \
      --no-probe
    ```

    OpenClaw's `mcp add` refuses to run while the local Gateway is up — stop it
    first, then verify with `openclaw mcp doctor drupal --probe`.

## No local install?

Point any client at PyPI directly:

```bash
drupal-mcp install --command 'uvx drupal-mcp-server'
```

## Verify

After installing, restart the client and ask it something that must touch
Drupal, for example *"list my content types"* (the agent should call
`content_list`). Client-side checks also help:

- Claude Code: `/mcp` shows the server and its connection state
- OpenClaw: `openclaw mcp status --verbose`, then `openclaw mcp probe drupal`
- Hermes: `hermes mcp test drupal`
- Pi: `pi mcp list`

## Security notes

The written config contains your `DRUPAL_*` values, including the password.
Project-scope files that live inside a repository (`.mcp.json`,
`opencode.json`) can end up committed — the installer warns when it writes
credentials into the current directory. Prefer `--scope local` for Claude
Code (stored outside the repo) or keep secrets in `~/.env`-style files
outside the project and reference them from the client yourself.
