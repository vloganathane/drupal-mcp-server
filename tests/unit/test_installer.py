"""Tests for the `drupal-mcp install` self-installer.

Every client shape here was verified against the real client's output or
official docs; the CLI-driven paths run stub executables that record their
argv so the constructed commands can be asserted without the real clients.
"""

from __future__ import annotations

import json
import stat
import tomllib
from pathlib import Path

import click
import pytest
import yaml
from click.testing import CliRunner

from drupal_mcp_server.installer import (
    CLIENT_IDS,
    Context,
    Result,
    collect_env,
    detect_clients,
    install_claude_code,
    install_codex,
    install_command,
    install_hermes,
    install_openclaw,
    install_opencode,
    install_pi,
    parse_env_pairs,
    resolve_command,
    stdio_entry,
)

ENV = {"DRUPAL_BASE_URL": "https://example.test", "DRUPAL_USERNAME": "admin"}


def make_ctx(tmp_path: Path, **overrides) -> Context:
    home = tmp_path / "home"
    cwd = tmp_path / "project"
    home.mkdir(exist_ok=True)
    cwd.mkdir(exist_ok=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    defaults = dict(
        command=["/opt/venv/bin/drupal-mcp"],
        env=dict(ENV),
        home=home,
        cwd=cwd,
        environ={"PATH": str(bin_dir)},
    )
    defaults.update(overrides)
    return Context(**defaults)


def stub_cli(tmp_path: Path, name: str) -> Path:
    """Create a stub executable that echoes its argv; returns the bin dir."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    script = bin_dir / name
    script.write_text('#!/bin/sh\necho "ran: $0 $@"\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return bin_dir


class TestEnvCollection:
    def test_precedence_is_dotenv_then_environment_then_flags(self, tmp_path):
        dotenv = tmp_path / ".env"
        dotenv.write_text(
            "DRUPAL_BASE_URL=https://from-file.test\n"
            "DRUPAL_USERNAME=file-user\n"
            "DRUPAL_PASSWORD=file-pass\n"
        )
        env = collect_env(
            {"DRUPAL_USERNAME": "flag-user"},
            environ={"DRUPAL_BASE_URL": "https://from-env.test"},
            dotenv_path=dotenv,
        )
        assert env["DRUPAL_BASE_URL"] == "https://from-env.test"
        assert env["DRUPAL_USERNAME"] == "flag-user"
        assert env["DRUPAL_PASSWORD"] == "file-pass"

    def test_implicit_sources_only_contribute_drupal_prefixed_keys(self, tmp_path):
        dotenv = tmp_path / ".env"
        dotenv.write_text("not-used=1\nDRUPAL_VERIFY_SSL=false\n")
        env = collect_env(
            {"MCP_TRANSPORT": "http"},
            environ={"OTHER": "x"},
            dotenv_path=dotenv,
        )
        assert env == {"DRUPAL_VERIFY_SSL": "false", "MCP_TRANSPORT": "http"}

    def test_missing_dotenv_file_is_fine(self, tmp_path):
        assert collect_env({}, environ={}, dotenv_path=tmp_path / "nope.env") == {}

    def test_parse_env_pairs_rejects_garbage(self):
        assert parse_env_pairs(("A=B",)) == {"A": "B"}
        with pytest.raises(click.BadParameter):
            parse_env_pairs(("NOEQUALS",))
        with pytest.raises(click.BadParameter):
            parse_env_pairs(("=novalue",))


class TestCommandResolution:
    def test_absolute_path_wins_when_script_on_path(self, tmp_path):
        stub_cli(tmp_path, "drupal-mcp")
        argv, warnings = resolve_command(None, environ={"PATH": str(tmp_path / "bin")})
        assert argv == [str(tmp_path / "bin" / "drupal-mcp")]
        assert warnings == []

    def test_uvx_fallback_when_script_missing(self, tmp_path):
        stub_cli(tmp_path, "uvx")
        argv, warnings = resolve_command(None, environ={"PATH": str(tmp_path / "bin")})
        assert argv == ["uvx", "--from", "drupal-mcp-server", "drupal-mcp"]
        assert warnings and "uvx" in warnings[0]

    def test_bare_name_and_warning_when_nothing_found(self, tmp_path):
        argv, warnings = resolve_command(None, environ={"PATH": str(tmp_path / "empty")})
        assert argv == ["drupal-mcp"]
        assert warnings and "not on PATH" in warnings[0]

    def test_override_is_shlex_split(self):
        argv, warnings = resolve_command("uvx --from . drupal-mcp-server")
        assert argv == ["uvx", "--from", ".", "drupal-mcp-server"]
        assert warnings == []


class TestMcpServersJsonShape:
    """Claude Desktop, Cursor, Windsurf and Claude project scope share the
    ``mcpServers`` shape; each must merge without harming other entries."""

    def test_claude_project_scope_writes_type_stdio_and_merges(self, tmp_path):
        ctx = make_ctx(tmp_path, claude_scope="project")
        (ctx.cwd / ".mcp.json").write_text(
            json.dumps({"mcpServers": {"other": {"command": "x"}}})
        )
        result = install_claude_code(ctx)
        assert result.status == "installed"
        data = json.loads((ctx.cwd / ".mcp.json").read_text())
        assert set(data["mcpServers"]) == {"other", "drupal"}
        entry = data["mcpServers"]["drupal"]
        assert entry["type"] == "stdio"
        assert entry["command"] == "/opt/venv/bin/drupal-mcp"
        assert entry["env"] == ENV

    def test_claude_without_cli_and_local_scope_fails_with_hint(self, tmp_path):
        ctx = make_ctx(tmp_path, claude_scope="local")
        result = install_claude_code(ctx)
        assert result.status == "failed"
        assert "--scope project" in result.detail

    def test_claude_cli_path_builds_verified_argv(self, tmp_path):
        stub_cli(tmp_path, "claude")
        ctx = make_ctx(tmp_path)
        result = install_claude_code(ctx)
        assert result.status == "installed"
        assert "claude" in result.detail

    def test_invalid_json_config_is_refused_not_clobbered(self, tmp_path):
        ctx = make_ctx(tmp_path)
        path = ctx.home / ".cursor" / "mcp.json"
        path.parent.mkdir(parents=True)
        path.write_text("{not json")
        result = install_command_result(tmp_path, "cursor", ctx)
        assert result.status == "failed"
        assert path.read_text() == "{not json"

    def test_desktop_path_follows_platform(self, tmp_path, monkeypatch):
        monkeypatch.setattr("drupal_mcp_server.installer.sys.platform", "darwin")
        ctx = make_ctx(tmp_path)
        result = install_command_result(tmp_path, "claude-desktop", ctx)
        assert result.status == "installed"
        assert result.detail.endswith(
            str(Path("Library") / "Application Support" / "Claude" / "claude_desktop_config.json")
        )


def install_command_result(tmp_path: Path, client: str, ctx: Context) -> Result:
    from drupal_mcp_server.installer import install_clients

    return install_clients(ctx, [client])[0]


class TestCodexToml:
    def test_fallback_writes_verified_block(self, tmp_path):
        ctx = make_ctx(tmp_path, command=["/opt/venv/bin/drupal-mcp", "--flag"])
        result = install_codex(ctx)
        assert result.status == "installed"
        text = (ctx.home / ".codex" / "config.toml").read_text()
        assert '[mcp_servers.drupal]' in text
        assert 'args = ["--flag"]' in text
        assert '[mcp_servers.drupal.env]' in text
        parsed = tomllib.loads(text)
        assert parsed["mcp_servers"]["drupal"]["command"] == "/opt/venv/bin/drupal-mcp"
        assert parsed["mcp_servers"]["drupal"]["env"] == ENV

    def test_existing_server_block_is_replaced_and_others_kept(self, tmp_path):
        ctx = make_ctx(tmp_path)
        path = ctx.home / ".codex" / "config.toml"
        path.parent.mkdir(parents=True)
        path.write_text(
            'model = "o3"\n\n'
            "[mcp_servers.other]\n"
            'command = "other-cmd"\n\n'
            "[mcp_servers.drupal]\n"
            'command = "stale-command"\n\n'
            "[mcp_servers.drupal.env]\n"
            'STALE = "value"\n'
        )
        result = install_codex(ctx)
        assert result.status == "installed"
        parsed = tomllib.loads(path.read_text())
        assert parsed["model"] == "o3"
        assert parsed["mcp_servers"]["other"]["command"] == "other-cmd"
        assert parsed["mcp_servers"]["drupal"]["command"] == "/opt/venv/bin/drupal-mcp"
        assert "STALE" not in parsed["mcp_servers"]["drupal"]["env"]
        assert parsed["mcp_servers"]["drupal"]["env"] == ENV

    def test_invalid_toml_is_refused(self, tmp_path):
        ctx = make_ctx(tmp_path)
        path = ctx.home / ".codex" / "config.toml"
        path.parent.mkdir(parents=True)
        path.write_text("= not toml")
        result = install_command_result(tmp_path, "codex", ctx)
        assert result.status == "failed"
        assert path.read_text() == "= not toml"

    def test_codex_cli_used_when_available(self, tmp_path):
        stub_cli(tmp_path, "codex")
        ctx = make_ctx(tmp_path)
        result = install_codex(ctx)
        assert result.status == "installed"
        assert not (ctx.home / ".codex" / "config.toml").exists()


class TestHermesYaml:
    def test_merges_and_backs_up(self, tmp_path):
        ctx = make_ctx(tmp_path)
        path = ctx.home / ".hermes" / "config.yaml"
        path.parent.mkdir(parents=True)
        path.write_text("mcp_servers:\n  other:\n    command: other-cmd\nmodel: foo\n")
        result = install_hermes(ctx)
        assert result.status == "installed"
        data = yaml.safe_load(path.read_text())
        assert data["model"] == "foo"
        assert data["mcp_servers"]["other"]["command"] == "other-cmd"
        assert data["mcp_servers"]["drupal"] == {
            "command": "/opt/venv/bin/drupal-mcp",
            "env": ENV,
        }
        assert path.with_suffix(".yaml.bak").is_file()

    def test_invalid_yaml_is_refused(self, tmp_path):
        ctx = make_ctx(tmp_path)
        path = ctx.home / ".hermes" / "config.yaml"
        path.parent.mkdir(parents=True)
        path.write_text("{{{: not yaml")
        result = install_command_result(tmp_path, "hermes", ctx)
        assert result.status == "failed"
        assert path.read_text() == "{{{: not yaml"

    def test_print_mode_emits_yaml_snippet(self, tmp_path):
        ctx = make_ctx(tmp_path, print_only=True)
        result = install_hermes(ctx)
        assert result.status == "printed"
        assert "mcp_servers:" in result.detail
        assert not (ctx.home / ".hermes" / "config.yaml").exists()


class TestOpencode:
    def test_fallback_nests_under_mcp_servers(self, tmp_path):
        ctx = make_ctx(tmp_path)
        result = install_opencode(ctx)
        assert result.status == "installed"
        data = json.loads((ctx.cwd / "opencode.json").read_text())
        entry = data["mcp"]["servers"]["drupal"]
        assert entry["type"] == "local"
        assert entry["command"] == ["/opt/venv/bin/drupal-mcp"]
        assert entry["environment"] == ENV
        assert data["$schema"] == "https://opencode.ai/config.json"

    def test_cli_used_when_available_and_global_flag_propagates(self, tmp_path):
        stub_cli(tmp_path, "opencode")
        ctx = make_ctx(tmp_path, opencode_global=True)
        result = install_opencode(ctx)
        assert result.status == "installed"
        assert not (ctx.cwd / "opencode.json").exists()


class TestPiAndOpenclaw:
    def test_pi_fallback_writes_mcp_servers_shape(self, tmp_path):
        ctx = make_ctx(tmp_path)
        result = install_pi(ctx)
        assert result.status == "installed"
        data = json.loads((ctx.home / ".pi" / "agent" / "mcp.json").read_text())
        assert data["mcpServers"]["drupal"]["command"] == "/opt/venv/bin/drupal-mcp"

    def test_pi_cli_used_when_available(self, tmp_path):
        stub_cli(tmp_path, "pi")
        ctx = make_ctx(tmp_path)
        assert install_pi(ctx).status == "installed"

    def test_openclaw_requires_cli_and_passes_no_probe(self, tmp_path):
        ctx = make_ctx(tmp_path)
        result = install_openclaw(ctx)
        assert result.status == "failed"
        assert "openclaw mcp add" in result.detail

        stub_cli(tmp_path, "openclaw")
        ctx = make_ctx(tmp_path, command=["drupal-mcp", "--stdio-flag"], env={"A": "b c"})
        result = install_openclaw(ctx)
        assert result.status == "installed"


class TestDetection:
    def test_detects_by_cli_and_config_paths(self, tmp_path):
        ctx = make_ctx(tmp_path)
        assert detect_clients(ctx) == []

        (ctx.home / ".claude").mkdir()
        (ctx.home / ".cursor").mkdir(parents=True, exist_ok=True)
        assert detect_clients(ctx) == ["claude-code", "cursor"]

        stub_cli(tmp_path, "codex")
        assert "codex" in detect_clients(ctx)

    def test_all_ids_have_installers(self):
        from drupal_mcp_server.installer import INSTALLERS

        assert set(INSTALLERS) == set(CLIENT_IDS)


class TestInstallCommand:
    def invoke(self, args, tmp_path, env=None):
        runner = CliRunner()
        environ = {"HOME": str(tmp_path / "home"), "PATH": str(tmp_path / "bin")}
        environ.update(env or {})
        return runner.invoke(install_command, args, env=environ)

    def test_print_mode_creates_nothing(self, tmp_path):
        (tmp_path / "home").mkdir()
        result = self.invoke(
            ["--client", "cursor", "--client", "hermes", "--client", "codex", "--print"],
            tmp_path,
        )
        assert result.exit_code == 0
        assert "cursor" in result.output
        assert not (tmp_path / "home" / ".cursor").exists()
        assert not (tmp_path / "home" / ".hermes").exists()

    def test_json_output_and_failure_exit_code(self, tmp_path):
        (tmp_path / "home").mkdir()
        stub_cli(tmp_path, "drupal-mcp")
        ok = self.invoke(
            ["--client", "cursor", "--json"], tmp_path, env={"DRUPAL_BASE_URL": "https://x.test"}
        )
        assert ok.exit_code == 0
        payload = json.loads(ok.output)
        assert payload[0]["client"] == "cursor"
        assert payload[0]["status"] == "installed"

        bad = self.invoke(
            ["--client", "openclaw", "--json"], tmp_path, env={"DRUPAL_BASE_URL": "https://x.test"}
        )
        assert bad.exit_code == 1
        assert json.loads(bad.output)[0]["status"] == "failed"

    def test_auto_detect_with_nothing_selected_errors(self, tmp_path):
        (tmp_path / "home").mkdir()
        result = self.invoke([], tmp_path)
        assert result.exit_code != 0
        assert "no MCP clients detected" in result.output

    def test_list_flag(self, tmp_path):
        (tmp_path / "home").mkdir()
        result = self.invoke(["--list"], tmp_path)
        assert result.exit_code == 0
        for client in CLIENT_IDS:
            assert client in result.output

    def test_explicit_env_flag_wins(self, tmp_path):
        (tmp_path / "home").mkdir()
        result = self.invoke(
            ["--client", "cursor", "--print", "--env", "DRUPAL_BASE_URL=https://flag.test"],
            tmp_path,
            env={"DRUPAL_BASE_URL": "https://env.test"},
        )
        assert result.exit_code == 0
        assert "https://flag.test" in result.output


class TestStdioEntry:
    def test_empty_args_and_no_env_omission(self):
        ctx = Context(command=["only-command"], env={})
        assert stdio_entry(ctx) == {"command": "only-command", "args": []}


class TestDispatch:
    def test_version_flag(self, capsys):
        from drupal_mcp_server import __version__
        from drupal_mcp_server.cli import main

        main(["--version"])
        assert capsys.readouterr().out.strip() == __version__

    def test_help_flag(self, capsys):
        from drupal_mcp_server.cli import main

        main(["--help"])
        out = capsys.readouterr().out
        assert "drupal-mcp install" in out

    def test_bare_invocation_starts_the_server(self, monkeypatch):
        called = {}
        monkeypatch.setattr(
            "drupal_mcp_server.server.run_server", lambda: called.setdefault("ran", True)
        )
        from drupal_mcp_server.cli import main

        main([])
        assert called.get("ran")

    def test_unknown_arguments_still_start_the_server(self, monkeypatch):
        called = {}
        monkeypatch.setattr(
            "drupal_mcp_server.server.run_server", lambda: called.setdefault("ran", True)
        )
        from drupal_mcp_server.cli import main

        main(["--something-unknown"])
        assert called.get("ran")

    def test_install_routes_to_installer(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            "drupal_mcp_server.installer.install_main",
            lambda args: seen.setdefault("args", args),
        )
        from drupal_mcp_server.cli import main

        main(["install", "--list"])
        assert seen["args"] == ["--list"]
