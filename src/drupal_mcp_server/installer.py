"""Register this server with local MCP clients.

`drupal-mcp install` detects which AI coding agents / MCP clients are on the
machine and writes this server into their configuration, so an agent (or a
human) never has to hand-assemble JSON, TOML or YAML snippets.

Two mechanisms, chosen per client:

* The client's own CLI when it is on PATH (Claude Code, Codex, OpenCode, Pi,
  OpenClaw) - it knows its current config schema better than we do.
* A direct write of the documented file format when it is not (Claude
  Desktop, Cursor, Windsurf, Hermes, and file fallbacks for the rest).

Every shape written here was verified against the corresponding client's
real output or official documentation:

* Claude Code project scope - ./.mcp.json ``mcpServers`` with ``type``
* Codex - ~/.codex/config.toml ``[mcp_servers.<name>]`` tables
* OpenCode - opencode.json ``mcp.servers`` (what `opencode mcp add` writes)
* Pi - ~/.pi/agent/mcp.json ``mcpServers``
* Hermes - ~/.hermes/config.yaml ``mcp_servers`` (written via pyyaml, not
  `hermes mcp add`, whose --env handling has open bugs that drop all but one
  variable: NousResearch/hermes-agent#37501 and #68944)
* Cursor / Windsurf / Claude Desktop - ``mcpServers`` JSON

Hermes' YAML and Codex' TOML are backed up / validated before replacing so a
malformed existing config can never be clobbered.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import click
import yaml
from dotenv import dotenv_values

SERVER_ENV_PREFIX = "DRUPAL_"
DEFAULT_NAME = "drupal"
_CLI_TIMEOUT = 60

CLIENT_IDS = (
    "claude-code",
    "claude-desktop",
    "cursor",
    "codex",
    "opencode",
    "windsurf",
    "pi",
    "hermes",
    "openclaw",
)


class InstallError(Exception):
    """A client could not be configured; message is shown to the user."""


@dataclass
class Context:
    """Everything the per-client writers need, gathered once."""

    name: str = DEFAULT_NAME
    command: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: Path = field(default_factory=Path.cwd)
    home: Path = field(default_factory=lambda: Path.home())
    environ: Mapping[str, str] = field(default_factory=lambda: os.environ)
    print_only: bool = False
    # Per-client options.
    claude_scope: str = "local"
    opencode_global: bool = False

    def which(self, executable: str) -> str | None:
        return shutil.which(executable, path=self.environ.get("PATH"))

    @property
    def has_credentials(self) -> bool:
        return any(
            any(word in key.upper() for word in ("PASSWORD", "TOKEN", "SECRET"))
            for key in self.env
        )


@dataclass
class Result:
    client: str
    status: str  # installed | printed | skipped | failed
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"client": self.client, "status": self.status, "detail": self.detail}


# --------------------------------------------------------------------------
# Environment and launch-command resolution
# --------------------------------------------------------------------------


def collect_env(
    explicit: Mapping[str, str],
    environ: Mapping[str, str] | None = None,
    dotenv_path: Path | None = None,
) -> dict[str, str]:
    """Merge DRUPAL_* settings from .env, the process env and --env flags.

    Precedence is dotenv < process environment < explicit flags: a value the
    caller exported wins over the file, and an explicit --env wins over both.
    Only DRUPAL_-prefixed keys are taken from implicit sources so unrelated
    shell variables never leak into client configs; explicit flags pass
    through untouched so anything (e.g. MCP_TRANSPORT) can be set on purpose.
    """
    environ = os.environ if environ is None else environ
    merged: dict[str, str] = {}
    if dotenv_path is not None and dotenv_path.is_file():
        for key, value in dotenv_values(dotenv_path).items():
            if value is not None and key.startswith(SERVER_ENV_PREFIX):
                merged[key] = value
    for key, value in environ.items():
        if key.startswith(SERVER_ENV_PREFIX):
            merged[key] = value
    merged.update(explicit)
    return merged


def parse_env_pairs(pairs: tuple[str, ...]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise click.BadParameter(f"expected KEY=VALUE, got {pair!r}")
        key, _, value = pair.partition("=")
        if not key:
            raise click.BadParameter(f"expected KEY=VALUE, got {pair!r}")
        parsed[key] = value
    return parsed


def resolve_command(
    override: str | None, environ: Mapping[str, str] | None = None
) -> tuple[list[str], list[str]]:
    """Pick the argv the client should spawn.

    An absolute path wins when the console script is on PATH, because GUI
    clients (Claude Desktop, Cursor) launch servers with a sanitized
    environment that does not include the shell's PATH. Without the script,
    `uvx drupal-mcp-server` runs straight from PyPI. Returns (argv, warnings).
    """
    environ = os.environ if environ is None else environ
    if override:
        argv = shlex.split(override)
        if not argv:
            raise click.BadParameter("--command is empty")
        return argv, []

    path = environ.get("PATH")
    script = shutil.which("drupal-mcp", path=path)
    if script:
        return [script], []
    if shutil.which("uvx", path=path):
        return ["uvx", "drupal-mcp-server"], [
            "drupal-mcp is not on PATH; the config will run `uvx drupal-mcp-server` instead"
        ]
    return ["drupal-mcp"], [
        "drupal-mcp is not on PATH; the config points at the bare command and will "
        "only work once the package is installed"
    ]


# --------------------------------------------------------------------------
# Shared config helpers
# --------------------------------------------------------------------------


def stdio_entry(ctx: Context, *, with_type: bool = False) -> dict[str, Any]:
    """Build one client's server entry from argv + env."""
    entry: dict[str, Any] = {}
    if with_type:
        entry["type"] = "stdio"
    entry["command"] = ctx.command[0]
    entry["args"] = ctx.command[1:]
    if ctx.env:
        entry["env"] = dict(ctx.env)
    return entry


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InstallError(f"{path} is not valid JSON ({exc}); not touching it") from exc
    if not isinstance(data, dict):
        raise InstallError(f"{path} does not contain a JSON object; not touching it")
    return data


def write_mcp_servers_json(
    path: Path, name: str, entry: dict[str, Any], *, key: str = "mcpServers"
) -> None:
    """Merge ``entry`` under ``key.name`` in a JSON config, preserving the rest."""
    data = _load_json(path)
    servers = data.setdefault(key, {})
    if not isinstance(servers, dict):
        raise InstallError(f'{path}: "{key}" is not an object; not touching it')
    servers[name] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _toml_str(value: str) -> str:
    """Quote a value as a TOML basic string (JSON escaping is compatible)."""
    return json.dumps(value)


def codex_toml_block(ctx: Context) -> str:
    lines = [f"[mcp_servers.{ctx.name}]", f"command = {_toml_str(ctx.command[0])}"]
    if len(ctx.command) > 1:
        args = ", ".join(_toml_str(a) for a in ctx.command[1:])
        lines.append(f"args = [{args}]")
    if ctx.env:
        lines.append("")
        lines.append(f"[mcp_servers.{ctx.name}.env]")
        for key, value in ctx.env.items():
            lines.append(f"{key} = {_toml_str(value)}")
    return "\n".join(lines) + "\n"


def write_codex_toml(path: Path, ctx: Context) -> None:
    """Replace (or append) this server's tables in ~/.codex/config.toml.

    Everything outside ``[mcp_servers.<name>]*`` is preserved byte-for-byte,
    and the result is re-parsed with tomllib before it is written, so a bad
    edit can never corrupt an existing Codex config.
    """
    import tomllib

    existing = ""
    if path.is_file():
        existing = path.read_text(encoding="utf-8")
        try:
            tomllib.loads(existing)
        except tomllib.TOMLDecodeError as exc:
            raise InstallError(f"{path} is not valid TOML ({exc}); not touching it") from exc

    headers = (f"[mcp_servers.{ctx.name}]", f"[mcp_servers.{ctx.name}.")
    kept: list[str] = []
    skipping = False
    for line in existing.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("["):
            # A header starts a new block; keep skipping only while it is one
            # of this server's tables.
            skipping = stripped == headers[0] or stripped.startswith(headers[1])
        if not skipping:
            kept.append(line)

    body = "".join(kept)
    if body and not body.endswith("\n"):
        body += "\n"
    if body and not body.endswith("\n\n"):
        body += "\n"
    candidate = body + codex_toml_block(ctx)
    try:
        tomllib.loads(candidate)
    except tomllib.TOMLDecodeError as exc:  # pragma: no cover - defensive
        raise InstallError(f"refusing to write malformed TOML to {path}: {exc}") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(candidate, encoding="utf-8")


def hermes_yaml_entry(ctx: Context) -> dict[str, Any]:
    entry: dict[str, Any] = {"command": ctx.command[0]}
    if len(ctx.command) > 1:
        entry["args"] = ctx.command[1:]
    if ctx.env:
        entry["env"] = dict(ctx.env)
    return entry


def write_hermes_yaml(path: Path, ctx: Context) -> None:
    """Merge this server into ~/.hermes/config.yaml under mcp_servers.

    pyyaml is used rather than `hermes mcp add` because that command's --env
    handling has open bugs (#37501, #68944) that drop environment variables.
    The existing file is backed up first and re-parsed before replacement;
    if it is not loadable YAML we refuse and the caller prints a snippet.
    """
    data: dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise InstallError(f"{path} is not valid YAML ({exc}); not touching it") from exc
        if loaded is not None:
            if not isinstance(loaded, dict):
                raise InstallError(f"{path} does not contain a YAML mapping; not touching it")
            data = loaded
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copyfile(path, backup)

    servers = data.get("mcp_servers")
    if servers is None:
        servers = {}
        data["mcp_servers"] = servers
    if not isinstance(servers, dict):
        raise InstallError(f'{path}: "mcp_servers" is not a mapping; not touching it')
    servers[ctx.name] = hermes_yaml_entry(ctx)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )


def _run_cli(argv: list[str], path: str | None = None) -> tuple[bool, str]:
    env = None
    if path is not None:
        env = {**os.environ, "PATH": path}
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=_CLI_TIMEOUT, check=False, env=env
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    output = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    return proc.returncode == 0, output


# --------------------------------------------------------------------------
# Client definitions: detection, CLI argv construction, file targets
# --------------------------------------------------------------------------


def _claude_desktop_dir(ctx: Context) -> Path:
    if sys.platform == "darwin":
        return ctx.home / "Library" / "Application Support" / "Claude"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", ctx.home)) / "Claude"
    return ctx.home / ".config" / "Claude"


def _claude_cli_argv(ctx: Context) -> list[str]:
    argv = ["claude", "mcp", "add", "--scope", ctx.claude_scope, ctx.name]
    for key, value in ctx.env.items():
        argv += ["-e", f"{key}={value}"]
    return argv + ["--", *ctx.command]


def _codex_cli_argv(ctx: Context) -> list[str]:
    argv = ["codex", "mcp", "add", ctx.name]
    for key, value in ctx.env.items():
        argv += ["--env", f"{key}={value}"]
    return argv + ["--", *ctx.command]


def _opencode_cli_argv(ctx: Context) -> list[str]:
    argv = ["opencode", "mcp", "add"]
    if ctx.opencode_global:
        argv.append("--global")
    argv.append(ctx.name)
    for key, value in ctx.env.items():
        argv += ["--env", f"{key}={value}"]
    return argv + ["--", *ctx.command]


def _pi_cli_argv(ctx: Context) -> list[str]:
    argv = ["pi", "mcp", "add", ctx.name]
    for key, value in ctx.env.items():
        argv += ["--env", f"{key}={value}"]
    return argv + ["--", *ctx.command]


def _openclaw_cli_argv(ctx: Context) -> list[str]:
    argv = ["openclaw", "mcp", "add", ctx.name, "--command", ctx.command[0]]
    for arg in ctx.command[1:]:
        argv += ["--arg", arg]
    for key, value in ctx.env.items():
        argv += ["--env", f"{key}={value}"]
    # Probing would start the server during install; --no-probe keeps the
    # write offline (the OpenClaw docs recommend `mcp doctor` afterwards).
    argv.append("--no-probe")
    return argv


def _exists(ctx: Context, *parts: str) -> bool:
    return (ctx.home.joinpath(*parts)).exists()


def detect_clients(ctx: Context) -> list[str]:
    """Clients that look installed: CLI on PATH or a known config path exists."""
    checks: dict[str, bool] = {
        "claude-code": bool(ctx.which("claude")) or _exists(ctx, ".claude") or _exists(ctx, ".claude.json"),
        "claude-desktop": _claude_desktop_dir(ctx).exists(),
        "cursor": bool(ctx.which("cursor")) or _exists(ctx, ".cursor"),
        "codex": bool(ctx.which("codex")) or _exists(ctx, ".codex"),
        "opencode": (
            bool(ctx.which("opencode"))
            or _exists(ctx, ".config", "opencode")
            or (ctx.cwd / "opencode.json").exists()
            or (ctx.cwd / "opencode.jsonc").exists()
        ),
        "windsurf": _exists(ctx, ".codeium", "windsurf"),
        "pi": bool(ctx.which("pi")) or _exists(ctx, ".pi"),
        "hermes": bool(ctx.which("hermes")) or _exists(ctx, ".hermes"),
        "openclaw": bool(ctx.which("openclaw")) or _exists(ctx, ".openclaw"),
    }
    return [client for client in CLIENT_IDS if checks[client]]


def _print_block(label: str, body: str) -> str:
    return f"{label}:\n{body}"


def _install_via_cli(
    ctx: Context,
    client: str,
    argv_factory: Callable[[Context], list[str]],
    *,
    fallback: Callable[[Context], Result],
) -> Result:
    """Run the client's CLI; fall back to a file write when it is absent."""
    argv = argv_factory(ctx)
    if ctx.which(argv[0]):
        if ctx.print_only:
            return Result(client, "printed", shlex.join(argv))
        ok, output = _run_cli(argv, path=ctx.environ.get("PATH"))
        if ok:
            return Result(client, "installed", output or shlex.join(argv))
        return Result(client, "failed", f"{argv[0]} failed: {output}")
    return fallback(ctx)


def install_claude_code(ctx: Context) -> Result:
    def fallback(c: Context) -> Result:
        if c.claude_scope != "project":
            # local/user scopes live in files only the `claude` CLI knows how
            # to edit, so without the CLI there is nothing we can safely write.
            if c.print_only:
                return Result("claude-code", "printed", shlex.join(_claude_cli_argv(c)))
            return Result(
                "claude-code",
                "failed",
                "the `claude` CLI was not found; run with --scope project to "
                "write ./.mcp.json instead",
            )
        path = c.cwd / ".mcp.json"
        entry = stdio_entry(c, with_type=True)
        if c.print_only:
            return Result(
                "claude-code",
                "printed",
                _print_block(str(path), json.dumps({"mcpServers": {c.name: entry}}, indent=2)),
            )
        write_mcp_servers_json(path, c.name, entry)
        return Result("claude-code", "installed", str(path))

    return _install_via_cli(ctx, "claude-code", _claude_cli_argv, fallback=fallback)


def install_claude_desktop(ctx: Context) -> Result:
    path = _claude_desktop_dir(ctx) / "claude_desktop_config.json"
    entry = stdio_entry(ctx)
    if ctx.print_only:
        return Result(
            "claude-desktop",
            "printed",
            _print_block(str(path), json.dumps({"mcpServers": {ctx.name: entry}}, indent=2)),
        )
    write_mcp_servers_json(path, ctx.name, entry)
    return Result("claude-desktop", "installed", str(path))


def install_cursor(ctx: Context) -> Result:
    path = ctx.home / ".cursor" / "mcp.json"
    entry = stdio_entry(ctx)
    if ctx.print_only:
        return Result(
            "cursor",
            "printed",
            _print_block(str(path), json.dumps({"mcpServers": {ctx.name: entry}}, indent=2)),
        )
    write_mcp_servers_json(path, ctx.name, entry)
    return Result("cursor", "installed", str(path))


def install_windsurf(ctx: Context) -> Result:
    path = ctx.home / ".codeium" / "windsurf" / "mcp_config.json"
    entry = stdio_entry(ctx)
    if ctx.print_only:
        return Result(
            "windsurf",
            "printed",
            _print_block(str(path), json.dumps({"mcpServers": {ctx.name: entry}}, indent=2)),
        )
    write_mcp_servers_json(path, ctx.name, entry)
    return Result("windsurf", "installed", str(path))


def install_codex(ctx: Context) -> Result:
    def fallback(c: Context) -> Result:
        path = c.home / ".codex" / "config.toml"
        if c.print_only:
            return Result(
                "codex",
                "printed",
                _print_block(str(path), codex_toml_block(c).rstrip("\n")),
            )
        write_codex_toml(path, c)
        return Result("codex", "installed", str(path))

    return _install_via_cli(ctx, "codex", _codex_cli_argv, fallback=fallback)


def install_opencode(ctx: Context) -> Result:
    def fallback(c: Context) -> Result:
        path = (
            c.home / ".config" / "opencode" / "opencode.json"
            if c.opencode_global
            else c.cwd / "opencode.json"
        )
        entry: dict[str, Any] = {
            "type": "local",
            "command": list(c.command),
        }
        if c.env:
            entry["environment"] = dict(c.env)
        if c.print_only:
            return Result(
                "opencode",
                "printed",
                _print_block(
                    str(path), json.dumps({"mcp": {"servers": {c.name: entry}}}, indent=2)
                ),
            )
        write_mcp_servers_json(path, c.name, entry, key="mcp") if _nested_needed(path) else None
        # OpenCode nests servers under mcp.servers, not mcp.<name>.
        _write_opencode(path, c.name, entry)
        return Result("opencode", "installed", str(path))

    return _install_via_cli(ctx, "opencode", _opencode_cli_argv, fallback=fallback)


def _nested_needed(path: Path) -> bool:  # pragma: no cover - retained for clarity
    return True


def _write_opencode(path: Path, name: str, entry: dict[str, Any]) -> None:
    data = _load_json(path)
    mcp = data.setdefault("mcp", {})
    if not isinstance(mcp, dict):
        raise InstallError(f'{path}: "mcp" is not an object; not touching it')
    servers = mcp.setdefault("servers", {})
    if not isinstance(servers, dict):
        raise InstallError(f'{path}: "mcp.servers" is not an object; not touching it')
    servers[name] = entry
    data.setdefault("$schema", "https://opencode.ai/config.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def install_pi(ctx: Context) -> Result:
    def fallback(c: Context) -> Result:
        path = c.home / ".pi" / "agent" / "mcp.json"
        entry = stdio_entry(c)
        if c.print_only:
            return Result(
                "pi",
                "printed",
                _print_block(str(path), json.dumps({"mcpServers": {c.name: entry}}, indent=2)),
            )
        write_mcp_servers_json(path, c.name, entry)
        return Result("pi", "installed", str(path))

    return _install_via_cli(ctx, "pi", _pi_cli_argv, fallback=fallback)


def install_hermes(ctx: Context) -> Result:
    path = ctx.home / ".hermes" / "config.yaml"
    if ctx.print_only:
        body = yaml.safe_dump(
            {"mcp_servers": {ctx.name: hermes_yaml_entry(ctx)}},
            sort_keys=False,
            default_flow_style=False,
        ).rstrip("\n")
        return Result("hermes", "printed", _print_block(str(path), body))
    write_hermes_yaml(path, ctx)
    return Result("hermes", "installed", str(path))


def install_openclaw(ctx: Context) -> Result:
    argv = _openclaw_cli_argv(ctx)
    if not ctx.which("openclaw"):
        if ctx.print_only:
            return Result("openclaw", "printed", shlex.join(argv))
        return Result(
            "openclaw",
            "failed",
            "the `openclaw` CLI was not found; run this instead: " + shlex.join(argv),
        )
    if ctx.print_only:
        return Result("openclaw", "printed", shlex.join(argv))
    ok, output = _run_cli(argv, path=ctx.environ.get("PATH"))
    if ok:
        return Result("openclaw", "installed", output or shlex.join(argv))
    return Result("openclaw", "failed", f"openclaw failed: {output}")


INSTALLERS = {
    "claude-code": install_claude_code,
    "claude-desktop": install_claude_desktop,
    "cursor": install_cursor,
    "codex": install_codex,
    "opencode": install_opencode,
    "windsurf": install_windsurf,
    "pi": install_pi,
    "hermes": install_hermes,
    "openclaw": install_openclaw,
}


def install_clients(ctx: Context, clients: list[str]) -> list[Result]:
    results: list[Result] = []
    for client in clients:
        try:
            results.append(INSTALLERS[client](ctx))
        except InstallError as exc:
            results.append(Result(client, "failed", str(exc)))
    return results


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _print_results(results: list[Result]) -> None:
    symbols = {
        "installed": "✓",
        "printed": "→",
        "skipped": "-",
        "failed": "✗",
    }
    for result in results:
        click.echo(f"{symbols[result.status]} {result.client}: {result.detail}")


def _print_list() -> None:
    click.echo("Supported clients:")
    for client in CLIENT_IDS:
        click.echo(f"  {client}")


@click.command(
    name="install",
    context_settings={"help_option_names": ["-h", "--help"]},
    help=(
        "Register this server with local MCP clients.\n\n"
        "With no --client, every detected client is configured. Values are "
        "gathered from ./.env, the process environment (DRUPAL_*) and --env."
    ),
)
@click.option(
    "--client",
    "clients",
    multiple=True,
    type=click.Choice(CLIENT_IDS),
    help="Configure only this client (repeatable).",
)
@click.option("--all", "configure_all", is_flag=True, help="Configure every supported client.")
@click.option("--list", "list_clients", is_flag=True, help="List supported clients and exit.")
@click.option("--name", default=DEFAULT_NAME, show_default=True, help="Server name in the config.")
@click.option(
    "--command",
    "command_override",
    default=None,
    help="Launch command (shlex-split), e.g. --command 'uvx drupal-mcp-server'.",
)
@click.option(
    "--env",
    "env_pairs",
    multiple=True,
    metavar="KEY=VALUE",
    help="Extra environment variable (repeatable); wins over the environment.",
)
@click.option(
    "--dotenv",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Env file to read DRUPAL_* values from (default: ./.env if present).",
)
@click.option(
    "--scope",
    type=click.Choice(["local", "user", "project"]),
    default="local",
    show_default=True,
    help="Claude Code configuration scope.",
)
@click.option(
    "--global",
    "opencode_global",
    is_flag=True,
    help="OpenCode: write the global config instead of the project one.",
)
@click.option("--print", "print_only", is_flag=True, help="Print configs/commands, write nothing.")
@click.option("--json", "json_out", is_flag=True, help="Emit results as JSON.")
def install_command(
    clients: tuple[str, ...],
    configure_all: bool,
    list_clients: bool,
    name: str,
    command_override: str | None,
    env_pairs: tuple[str, ...],
    dotenv: Path | None,
    scope: str,
    opencode_global: bool,
    print_only: bool,
    json_out: bool,
) -> None:
    if list_clients:
        _print_list()
        return

    cwd = Path.cwd()
    env_file = dotenv if dotenv is not None else (cwd / ".env")
    env = collect_env(parse_env_pairs(env_pairs), dotenv_path=env_file)
    command, warnings = resolve_command(command_override)

    ctx = Context(
        name=name,
        command=command,
        env=env,
        cwd=cwd,
        print_only=print_only,
        claude_scope=scope,
        opencode_global=opencode_global,
    )

    if configure_all:
        selected = list(CLIENT_IDS)
    elif clients:
        selected = [client for client in CLIENT_IDS if client in clients]
    else:
        selected = detect_clients(ctx)
        if not selected:
            raise click.ClickException(
                "no MCP clients detected; pass --client (see --list) or --all"
            )

    if not print_only and not env:
        warnings.append(
            "no DRUPAL_* settings found - set DRUPAL_BASE_URL (and credentials) "
            f"in {env_file} or via --env before starting the server"
        )

    results = install_clients(ctx, selected)

    for warning in warnings:
        click.echo(f"warning: {warning}", err=True)

    if ctx.has_credentials and not print_only:
        for result in results:
            if result.status == "installed" and str(ctx.cwd) in result.detail:
                click.echo(
                    "warning: credentials were written to a file inside the current "
                    "directory - make sure it is not committed",
                    err=True,
                )
                break

    if json_out:
        click.echo(json.dumps([result.as_dict() for result in results], indent=2))
    else:
        _print_results(results)

    if any(result.status == "failed" for result in results):
        raise SystemExit(1)


def install_main(args: list[str]) -> None:
    install_command.main(args=args, prog_name="drupal-mcp install")
